"""Controlled paired-query experiment: two BM25 searches, fused before dense fusion.

Uses existing reviewed EN/VI translations, not automatic translation. The 48
original-language cases are 24 paired intents, not 48 independent questions.
"""
import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean

from evaluate_two_document_benchmark import ROOT, SOURCES
from core.database.document_chunks_repository import DocumentChunkRepository
from core.evaluation.retrieval_metrics import recall_at_k, reciprocal_rank, ndcg_at_k
from core.retrieval.retrieval import make_chunk_id


def fuse(rankings, weights, k=60):
    scores = {}
    for ranking, weight in zip(rankings, weights):
        for rank, chunk_id in enumerate(dict.fromkeys(ranking), 1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + weight / (k + rank)
    return sorted(scores, key=lambda chunk_id: (-scores[chunk_id], chunk_id))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--device', choices=('cpu', 'cuda'), default='cuda')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/evaluation/retrieval/scoped-bilingual-20261015.json')
    parser.add_argument('--self-check', action='store_true')
    args = parser.parse_args()
    if args.self_check:
        assert fuse([['a', 'b'], ['b', 'c']], [1.0, 1.0]) == ['b', 'a', 'c']
        assert fuse([['a', 'a', 'b']], [1.0]) == ['a', 'b']
        assert fuse([[], []], [1.0, 1.0]) == []
        print('Bilingual rank-fusion checks passed')
        return
    files = {lang: ROOT / f'data/evaluation/long_hau_2008_cases{suffix}.json' for lang, suffix in [('en', '_en'), ('vn', '')]}
    cases = {lang: json.loads(path.read_bytes()) for lang, path in files.items()}
    assert [x['id'] for x in cases['en']] == [x['id'] for x in cases['vn']]
    assert len(cases['en']) == 24
    document_ids = list(SOURCES.values())
    repository = DocumentChunkRepository()
    try:
        repository.conn.rollback()
        repository.conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
        repository.conn.execute("SET LOCAL statement_timeout='30s'")
        rows = repository.conn.execute(
            "SELECT c.chunk_index, c.content, c.metadata, c.embedding::text, "
            "d.document_id, d.allowed_roles, d.fiscal_year, d.company "
            "FROM document_chunks c JOIN documents d ON d.document_id = c.metadata->>'document_id' "
            "WHERE d.document_id = ANY(%s::text[]) AND coalesce(d.processing_status, 'ready')='ready' "
            "ORDER BY d.document_id, c.chunk_index, c.id", (document_ids,),
        ).fetchall()
        corpus_hash = hashlib.sha256(json.dumps(rows, ensure_ascii=False, default=str).encode()).hexdigest()
        baselines = {}
        for lang in files:
            baseline = json.loads((ROOT / f'artifacts/evaluation/retrieval/scoped-{lang}-gpu.json').read_text())
            assert baseline['scoped_corpus_sha256'] == corpus_hash, 'Corpus changed since baseline'
            assert baseline['cases_sha256'] == hashlib.sha256(files[lang].read_bytes()).hexdigest()
            baselines[lang] = baseline['summary']
        models = {r[2].get('embedding_model') for r in rows}
        assert len(models) == 1 and None not in models
        model_id = models.pop()
        from langchain_huggingface import HuggingFaceEmbeddings
        embedding = HuggingFaceEmbeddings(model_name=model_id, model_kwargs={'device': args.device})
        indexed = {(r[4], r[0]): r for r in rows}
        results = []
        for english, vietnamese in zip(cases['en'], cases['vn']):
            assert english['evidence'] == vietnamese['evidence']
            gold = set()
            for item in english['evidence']:
                key = (SOURCES[item['source']], item['chunk_index'])
                assert key in indexed and indexed[key][2].get('page_number') == item['page_number']
                gold.add(make_chunk_id(*key))
            lexical_rankings = []
            for case in (english, vietnamese):
                chunks = repository.similarity_search(None, 100, query=case['question'], method='bm25', document_ids=document_ids, roles=['admin'])
                lexical_rankings.append([make_chunk_id(c.document_id, c.chunk_index) for c in chunks])
            bilingual = fuse(lexical_rankings, [1.0, 1.0])
            for lang, case in [('en', english), ('vn', vietnamese)]:
                vector = embedding.embed_query(case['question'])
                dense_chunks = repository.similarity_search(vector, 100, query=case['question'], method='dense', document_ids=document_ids, roles=['admin'])
                dense = [make_chunk_id(c.document_id, c.chunk_index) for c in dense_chunks]
                # Keep the production top-100 candidate budget for final dense/lexical fusion.
                hybrid = fuse([dense, bilingual[:100]], [1.0, 2.0])
                for method, ranking in [('bilingual_bm25', bilingual), ('bilingual_hybrid', hybrid)]:
                    ranked = ranking[:10]
                    assert all(x.rsplit('::chunk::', 1)[0] in document_ids for x in ranked)
                    results.append({'id': case['id'], 'language': lang, 'question': case['question'],
                                    'lexical_queries': [english['question'], vietnamese['question']],
                                    'method': method, 'gold_chunk_ids': sorted(gold), 'ranked_chunk_ids': ranked,
                                    'metrics': {'recall_at_k': recall_at_k(gold, ranked, 10),
                                                'precision_at_k': len(gold.intersection(ranked)) / len(ranked) if ranked else 0.0,
                                                'mrr': reciprocal_rank(gold, ranked), 'ndcg_at_k': ndcg_at_k(gold, ranked, 10)}})
            print(f"{english['id']}: both original languages evaluated; scope verified", flush=True)
        summary = {}
        for lang in files:
            summary[lang] = dict(baselines[lang])
            for method in ('bilingual_bm25', 'bilingual_hybrid'):
                selected = [x for x in results if x['language'] == lang and x['method'] == method]
                summary[lang][method] = {key: round(mean(x['metrics'][key] for x in selected), 4) for key in selected[0]['metrics']}
        report = {'created_at': datetime.now(timezone.utc).isoformat(), 'scope': {'document_ids': document_ids, 'roles': ['admin'], 'chunks': len(rows)},
                  'corpus_sha256': corpus_hash, 'case_hashes': {lang: hashlib.sha256(path.read_bytes()).hexdigest() for lang, path in files.items()},
                  'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                  'embedding_model': model_id, 'device': args.device, 'paired_intents': 24, 'original_query_cases': 48,
                  'configuration': {'top_k': 10, 'candidate_k': 100, 'rrf_k': 60, 'lexical_en_vn_weights': [1.0, 1.0], 'dense_bilingual_weights': [1.0, 2.0]},
                  'limitations': 'Controlled use of reviewed paired translations, not production automatic translation. 48 cases represent 24 paired intents. Two-stage rank fusion has deterministic chunk-ID tie breaking; ranking policy differs from SQL hybrid. No database writes or generation calls. Baseline aggregates are verified saved runs, not new timing measurements.',
                  'summary': summary, 'results': results}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
        print(json.dumps(summary, indent=2))
    finally:
        repository.close()


if __name__ == '__main__':
    main()