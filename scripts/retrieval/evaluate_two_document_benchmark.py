"""Compare retrieval methods on An's questions, scoped to the same two reports."""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))
from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.evaluation.retrieval_metrics import recall_at_k, reciprocal_rank, ndcg_at_k
from core.retrieval.retrieval import RetrievalRequest, make_chunk_id
from core.retrieval.retrieval_service import RetrievalService

SOURCES = {
    'annual_report': 'UPLOAD-11e62199551047c0a1ddcd5e6684a1c1',
    'long_hau_fs': 'UPLOAD-5149fb823530440da1a2f09704c695d6',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases', type=Path, default=ROOT / 'data/evaluation/long_hau_2008_cases_en.json')
    parser.add_argument('--methods', nargs='+', choices=('dense', 'bm25', 'hybrid'), default=['dense', 'bm25', 'hybrid'])
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--top-k', type=int, default=10)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cpu')
    parser.add_argument('--dense-weight', type=float, default=1.0)
    parser.add_argument('--bm25-weight', type=float, default=2.0)
    parser.add_argument('--annual-report-id', default=SOURCES['annual_report'])
    parser.add_argument('--long-hau-fs-id', default=SOURCES['long_hau_fs'])
    args = parser.parse_args()
    if not 1 <= args.top_k <= 100:
        parser.error('--top-k must be between 1 and 100')
    sources = {'annual_report': args.annual_report_id, 'long_hau_fs': args.long_hau_fs_id}
    document_ids = list(sources.values())
    if len(set(document_ids)) != 2:
        parser.error('Two distinct document IDs are required')
    case_bytes = args.cases.read_bytes()
    cases = json.loads(case_bytes)
    if not cases:
        parser.error('Cases must not be empty')
    repository = DocumentChunkRepository()
    try:
        repository.conn.rollback()
        repository.conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        repository.conn.execute("SET LOCAL statement_timeout = '30s'")
        rows = repository.conn.execute(
            "SELECT c.chunk_index, c.content, c.metadata, c.embedding::text, "
            "d.document_id, d.allowed_roles, d.fiscal_year, d.company "
            "FROM document_chunks c JOIN documents d ON d.document_id = c.metadata->>'document_id' "
            "WHERE d.document_id = ANY(%s::text[]) AND coalesce(d.processing_status, 'ready')='ready' "
            "ORDER BY d.document_id, c.chunk_index, c.id", (document_ids,),
        ).fetchall()
        if {row[4] for row in rows} != set(document_ids):
            raise ValueError('Both scoped documents must exist, be ready, and have indexed chunks')
        models = {row[2].get('embedding_model') for row in rows}
        if len(models) != 1 or None in models:
            raise ValueError('Scoped chunks must identify one compatible embedding model')
        model_id = models.pop()
        indexed = {(row[4], row[0]): row for row in rows}
        embedding = None
        if any(m != 'bm25' for m in args.methods):
            from langchain_huggingface import HuggingFaceEmbeddings
            embedding = EmbeddingService(
                model_name=model_id,
                backend=HuggingFaceEmbeddings(model_name=model_id, model_kwargs={'device': args.device}),
            )
        service = RetrievalService(embedding, repository)
        results = []
        for case in cases:
            gold = set()
            for item in case['evidence']:
                doc_id = sources[item['source']]
                row = indexed.get((doc_id, item['chunk_index']))
                if row is None or row[2].get('page_number') != item['page_number']:
                    raise ValueError(f"{case['id']}: gold chunk missing or page mismatch")
                gold.add(make_chunk_id(doc_id, item['chunk_index']))
            if not gold:
                raise ValueError(f"{case['id']}: gold chunks are required")
            vector = embedding.embed_query(case['question']) if embedding else None
            # Reuse the same query vector across methods, excluding embedding time from search latency.
            service.embedding_service = SimpleNamespace(embed_query=lambda query: vector)
            for method in args.methods:
                response = service.retrieve(
                    RetrievalRequest(query=case['question'], top_k=args.top_k),
                    document_ids=document_ids, roles=['admin'], method=method,
                    dense_weight=args.dense_weight, bm25_weight=args.bm25_weight,
                )
                if any(chunk.document_id not in document_ids for chunk in response.results):
                    raise AssertionError('Retrieval escaped the two-document scope')
                ranked = [chunk.chunk_id for chunk in response.results]
                results.append({
                    'id': case['id'], 'question': case['question'], 'method': method,
                    'gold_chunk_ids': sorted(gold), 'ranked_chunk_ids': ranked,
                    'search_latency_ms': response.latency_ms,
                    'metrics': {
                        'recall_at_k': recall_at_k(gold, ranked, args.top_k),
                        'precision_at_k': len(gold.intersection(ranked)) / len(ranked) if ranked else 0.0,
                        'mrr': reciprocal_rank(gold, ranked),
                        'ndcg_at_k': ndcg_at_k(gold, ranked, args.top_k),
                    },
                })
            print(f"{case['id']}: scope verified for {', '.join(args.methods)}", flush=True)
        report = {
            'created_at': datetime.now(timezone.utc).isoformat(),
            'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'retrieval_code_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                      for path in sorted((ROOT / 'src/core/retrieval').rglob('*.py'))},
            'git_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
            'scope': {'document_ids': document_ids, 'roles': ['admin'], 'chunks': len(rows)},
            'cases_sha256': hashlib.sha256(case_bytes).hexdigest(),
            'scoped_corpus_sha256': hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest(),
            'embedding_model': model_id, 'embedding_device': args.device, 'top_k': args.top_k,
            'dense_weight': args.dense_weight, 'bm25_weight': args.bm25_weight, 'rrf_k': 60,
            'case_count': len(cases), 'methods': args.methods,
            'limitations': 'Scoped exact-chunk benchmark, not mixed-corpus search or answer quality. Search latency excludes query embedding and model load. Source cases copied unchanged from QuocAn 3ea4f43.',
            'results': results, 'summary': {},
        }
        for method in args.methods:
            selected = [row for row in results if row['method'] == method]
            report['summary'][method] = {key: round(mean(row['metrics'][key] for row in selected), 4) for key in selected[0]['metrics']}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report['summary'], indent=2))
    finally:
        repository.close()


if __name__ == '__main__':
    main()