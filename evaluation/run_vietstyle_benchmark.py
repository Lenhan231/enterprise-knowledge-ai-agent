import argparse, csv, json, os, sys
from pathlib import Path
sys.path[:0] = [str(Path(__file__).resolve().parents[1] / 'src')]
from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings import EmbeddingService
from core.llm.groq_provider import GroqProvider
from core.llm.openai_compatible_provider import OpenAICompatibleProvider
from core.llm.models import BENCHMARK_MODELS
from core.rag.rag_service import RAGService
from core.retrieval.retrieval_service import RetrievalService
from core.retrieval.retrieval import RetrievalRequest

ROOT = Path(__file__).resolve().parents[1]
CSV = Path(r'C:\Users\Admin\Downloads\VietStyle_RAG_Benchmark_20_Questions.csv')
OUT = ROOT / 'artifacts/benchmark/vietstyle_q01-20_latest_retrieval.json'
IDS = ['UPLOAD-01e597aeef0d43a9867718fabf2b3854','UPLOAD-f28de4382cfa4bf9a05228762b7243f3','UPLOAD-7a57f65f5ea3418eb42f0d49d3905acf','UPLOAD-cdd0d21cdce346e0992ee6b05219e40c','UPLOAD-a8b54a0cd83e44e8af22437eeba5ba65']

parser = argparse.ArgumentParser()
parser.add_argument('--model', choices=('gemini_flash', 'qwen3'), required=True)
parser.add_argument('--output', type=Path, default=OUT)
args = parser.parse_args()
OUT = args.output
rows = list(csv.DictReader(CSV.open(encoding='utf-8-sig', newline='')))
repo = DocumentChunkRepository()
model_config = BENCHMARK_MODELS[args.model]
api_key = next(os.environ[name] for name in model_config['api_key_env'] if os.environ.get(name))
llm = (GroqProvider(model=model_config['model'], api_key=api_key)
       if 'groq.com' in model_config['base_url'] else
       OpenAICompatibleProvider(model=model_config['model'], base_url=model_config['base_url'], api_key=api_key))
try:
    repo.conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
    repo.conn.execute("SET LOCAL statement_timeout='60s'")
    models = {r[0] for r in repo.conn.execute("SELECT DISTINCT metadata->>'embedding_model' FROM document_chunks WHERE metadata->>'document_id'=ANY(%s::text[])", (IDS,)).fetchall()}
    if len(models) != 1:
        raise RuntimeError(f'Expected one embedding model, found {models}')
    embedding = EmbeddingService(model_name=models.pop())
    retrieval = RetrievalService(embedding_service=embedding, repository=repo)
    rag = RAGService(retrieval_service=retrieval, llm=llm)
    report = {'benchmark':'VietStyle RAG Benchmark 20 Questions','model':args.model,'model_name':model_config['model'],'retrieval_source':'Huy latest committed retrieval (hybrid)','embedding_model':embedding.model_name,'top_k':10,'scope_document_ids':IDS,'scope_note':'README.txt is not indexed; Q01 therefore cannot retrieve that expected source.','results':[]}
    for row in rows:
        q = row['Câu hỏi']
        contexts = rag.retrieve_contexts(q, limit=10, company='Commerce Demo', roles=['admin'], retrieval_method='hybrid')
        try:
            answer = rag.generate_from_contexts(q, contexts)
            generated = {'answer': answer.answer, 'source_ids': answer.source_ids, 'insufficient_context': answer.insufficient_context}
        except Exception as e:
            generated = {'error': type(e).__name__ + ': ' + str(e)}
        expected = [x.strip() for x in row['Nguồn mong đợi'].split(';') if x.strip()]
        found = sorted({Path(c['document_name']).name for c in contexts} & set(expected))
        report['results'].append({'id':row['ID'],'question':q,'reference_answer':row['Đáp án chuẩn'],'expected_sources':expected,'found_expected_sources':found,'source_recall_at_10':round(len(found)/len(expected),4) if expected else 0,'policy_id':row['Policy ID'],'scoring_criteria':row['Tiêu chí chấm'],'retrieved_contexts':contexts,'generated':generated})
        print(f"{row['ID']}: source_recall={report['results'][-1]['source_recall_at_10']:.2f}", flush=True)
    report['summary']={'question_count':len(report['results']),'mean_source_recall_at_10':round(sum(x['source_recall_at_10'] for x in report['results'])/len(report['results']),4),'generation_completed':sum('answer' in x['generated'] for x in report['results'])}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Saved {OUT}')
finally:
    try: repo.conn.rollback()
    except Exception: pass
    repo.close()
    if hasattr(llm, 'close'):
        llm.close()
