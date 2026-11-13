"""Frozen, append-only Knowledge/Invoice benchmark. See KNOWLEDGE_INVOICE_PROTOCOL.md."""
from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import re
import statistics
import subprocess
import sys
import time

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from evaluation.knowledge_invoice_cases import KNOWLEDGE, INVOICES
from evaluation.run_inventory_agents_benchmark import read_jsonl, append, save, encode
from evaluation.inventory_benchmark_metrics import compare_rows, sql_numerical_accuracy

POLICY = 'artifacts/datasets/vietstyle-operations-vi-v1/VietStyle_Enterprise_Operating_Policy_v1.0_VN.md'
DOC = 'UPLOAD-5f3724762c5e4146b9f85d3696a6f919'
CONFIG = dict(agent_model='qwen/qwen3.8-27b', temperature=0, top_k=5,
    retrieval_method='translated_hybrid_rerank', embedding_model='intfloat/multilingual-e5-base',
    embedding_revision='d128750597153bb5987e10b1c3493a34e5a4502a',
    reranker_model='BAAI/bge-reranker-v2-m3', reranker_revision='953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e',
    reranker_quantize='float32', cpu_threads=2, document_id=DOC, roles=['employee'],
    historical_source_revision='fed9824', evaluation_harness_revision='6bf2f73',
    multiquery=False, claim_verification=False, judge_model='gpt-5.6-luna', judge_reasoning='medium',
    model_startup='preload_outside_request', hf_hub_offline=True, context_max_chars=24000, completeness_rule=False)


def digest(value):
    data = value if isinstance(value, bytes) else json.dumps(value, ensure_ascii=False, sort_keys=True, default=encode).encode()
    return hashlib.sha256(data).hexdigest()


def assert_runtime_isolation():
    loaded = {}
    for name, module in list(sys.modules.items()):
        if name.split('.')[0] not in {'core', 'evaluation'}:
            continue
        filename = getattr(module, '__file__', None)
        if filename and not Path(filename).resolve().is_relative_to(ROOT):
            raise RuntimeError(f'Import escaped isolated runtime: {name}: {filename}')
        if filename:
            path = Path(filename).resolve()
            loaded[name] = dict(path=str(path.relative_to(ROOT)), sha256=digest(path.read_bytes()))
    return loaded


def immutable_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if json.loads(path.read_text(encoding='utf-8')) != json.loads(json.dumps(value, default=encode)):
            raise ValueError(f'Frozen artifact differs: {path.name}; use a new cohort')
        return
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, default=encode, allow_nan=False) + '\n')


def append_once(path, row, keys):
    if any(all(old.get(k) == row.get(k) for k in keys) for old in read_jsonl(path)):
        raise ValueError(f'Record already exists: {[row.get(k) for k in keys]}')
    path.parent.mkdir(parents=True, exist_ok=True)
    append(path, row)


def source_hashes():
    paths = [*ROOT.joinpath('src').rglob('*.py'), *ROOT.joinpath('data/semantic').rglob('*.*'),
        ROOT / 'evaluation/run_knowledge_invoice_benchmark.py', ROOT / 'evaluation/knowledge_invoice_cases.py',
        ROOT / 'evaluation/ragas_judge.py', ROOT / 'evaluation/KNOWLEDGE_INVOICE_PROTOCOL.md']
    return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sorted(paths)}


def historical_hashes():
    names = subprocess.check_output(['git', 'ls-files', 'artifacts/evaluation'], cwd=ROOT, text=True).splitlines()
    # Document-parser experiments are unrelated and include paths beyond Windows' checkout limit.
    return {name: digest((ROOT / name).read_bytes()) for name in names if '/document-pipelines/' not in name}


def citation_audit(answer, contexts, pages, abstained):
    cited = set(re.findall(r'\[(S\d+)\]', answer))
    by_id = {c['source_id']: c for c in contexts}
    valid = cited & by_id.keys()
    expected = {p + 2 for p in pages}
    hits = sum(by_id[s].get('metadata', {}).get('page_number') in expected for s in valid)
    return dict(citation_validity=len(valid)/len(cited) if cited else (None if abstained else 0),
        expected_page_precision=hits/len(valid) if valid else None,
        unknown_citations=sorted(cited-by_id.keys()), cited=sorted(cited), expected_physical_pages=sorted(expected))


def readonly_connection(url):
    import psycopg
    from psycopg.rows import dict_row
    return psycopg.connect(url, connect_timeout=15, row_factory=dict_row,
        options='-c default_transaction_read_only=on -c statement_timeout=60000')


def database_snapshot():
    with readonly_connection(os.environ['ANALYTICS_DATABASE_URL']) as connection:
        schema = connection.execute("SELECT table_name,column_name,data_type,is_nullable FROM information_schema.columns "
            "WHERE table_schema='commerce' AND table_name IN ('invoices','invoice_items') ORDER BY table_name,ordinal_position").fetchall()
        keys = connection.execute("SELECT conrelid::regclass::text AS relation,pg_get_constraintdef(oid) AS definition "
            "FROM pg_constraint WHERE conrelid IN ('commerce.invoices'::regclass,'commerce.invoice_items'::regclass) ORDER BY 1,2").fetchall()
        role = connection.execute("SELECT current_user AS role,current_setting('transaction_read_only') AS readonly").fetchone()
        invoices = connection.execute('SELECT invoice_id,source_filename,invoice_no,invoice_date,buyer,seller,subtotal,tax_amount,total_amount,currency FROM commerce.invoices ORDER BY invoice_id').fetchall()
        items = connection.execute('SELECT invoice_id,line_no,description,unit,quantity,unit_price,amount FROM commerce.invoice_items ORDER BY invoice_id,line_no').fetchall()
        refs = [connection.execute(sql).fetchall() for _, sql in INVOICES]
    with readonly_connection(os.environ['DATABASE_URL']) as connection:
        document = connection.execute('SELECT document_id,storage_path,processing_status FROM public.documents WHERE document_id=%s', (DOC,)).fetchone()
        chunks = connection.execute("SELECT document_name,chunk_index,content,metadata FROM public.document_chunks WHERE metadata->>'document_id'=%s ORDER BY chunk_index,id", (DOC,)).fetchall()
        if not document or document['processing_status'] != 'ready' or not chunks:
            raise ValueError('Approved policy is not ready/indexed')
    return dict(schema=schema, keys=keys, role=role, invoice_rows=len(invoices), item_rows=len(items),
        invoice_data_sha256=digest([invoices, items]), references=refs, policy_document=document,
        corpus_sha256=digest(chunks), chunks=len(chunks), embedding_models=sorted({c['metadata'].get('embedding_model', '') for c in chunks}))


def freeze(out):
    assert_runtime_isolation()
    out.mkdir(parents=True, exist_ok=True)
    if (out / 'manifest.json').exists():
        verify(out)
        return
    snapshot = database_snapshot()
    policy = (ROOT / POLICY).read_text(encoding='utf-8')
    pages = {int(m[1]): m[2].strip() for m in re.finditer(r'TRANG CHÍNH SÁCH (\d+)\s*\|([^\n]*\n[\s\S]*?)(?=TRANG CHÍNH SÁCH \d+\s*\||\Z)', policy)}
    cases = dict(knowledge=[dict(id=f'K{i:02}', question=q, reference=r, policy_pages=p,
        should_abstain=i>25, reference_passages={str(page): pages[page] for page in p})
        for i, (q, r, p) in enumerate(KNOWLEDGE, 1)],
        invoice=[dict(id=f'I{i:02}', question=q, reference_sql=sql, reference_rows=rows)
            for i, ((q, sql), rows) in enumerate(zip(INVOICES, snapshot['references']), 1)])
    immutable_json(out / 'cases.json', cases)
    immutable_json(out / 'database-before.json', snapshot)
    immutable_json(out / 'manifest.json', dict(dataset_versions=['vietstyle-inventory-knowledge-30-v1','commerce-invoice-10-v1'],
        created_at=datetime.now(timezone.utc).isoformat(), application_revision=git('rev-parse','HEAD'),
        parents=git('show','-s','--format=%P','HEAD').split(), main_revision=git('rev-parse','origin/main'),
        quocan_revision=git('rev-parse','QuocAn'), remote_quocan_revision=git('rev-parse','origin/QuocAn'),
        config=CONFIG, cases_sha256=digest((out/'cases.json').read_bytes()), policy_sha256=digest((ROOT/POLICY).read_bytes()),
        source_hashes=source_hashes(), preserved_history=historical_hashes(),
        packages={name:importlib.metadata.version(name) for name in ['ragas','sqlglot','openai','sentence-transformers','psycopg']},
        reference_status='Independent author-written, policy-grounded references and read-only SQL oracles; not externally certified'))


def git(*args):
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def verify(out):
    assert_runtime_isolation()
    manifest = json.loads((out/'manifest.json').read_text(encoding='utf-8'))
    if source_hashes() != manifest['source_hashes'] or CONFIG != manifest['config']:
        raise ValueError('Application/evaluator source or configuration changed; use a new cohort')
    if digest((out/'cases.json').read_bytes()) != manifest['cases_sha256']:
        raise ValueError('Frozen questions/references changed')
    for name, checksum in manifest['preserved_history'].items():
        if digest((ROOT/name).read_bytes()) != checksum:
            raise ValueError(f'Historical artifact changed: {name}')
    return manifest


async def generate(out, group, ids):
    verify(out)
    from core.models.agents import AgentRequest, VerifiedIdentity
    from core.llm.groq_provider import GroqProvider
    from core.agents.knowledge_agent import KnowledgeAgent
    from core.agents.sql_analytics_agent import SQLAnalyticsAgent
    from core.database.commerce_repository import create_repository_from_env
    from core.rag.rag_service import RAGService
    from core.database.document_chunks_repository import DocumentChunkRepository
    from core.retrieval.retrieval_service import RetrievalService
    calls, contexts = [], []

    class RecordedProvider(GroqProvider):
        def generate(self, prompt, **kwargs):
            start = time.perf_counter()
            row = dict(prompt_sha256=digest(prompt.encode()), max_output_tokens=kwargs.get('max_output_tokens',1000))
            try:
                response = super().generate(prompt, **kwargs)
                row.update(response=response, usage=self.last_usage)
                return response
            except Exception as error:
                row['error_type'] = type(error).__name__
                raise
            finally:
                row['elapsed_seconds'] = time.perf_counter()-start
                calls.append(row)

    provider = RecordedProvider(model=CONFIG['agent_model'], temperature=0)
    if group == 'knowledge':
        import torch
        torch.set_num_threads(CONFIG['cpu_threads'])
        startup = time.perf_counter()
        from core.embeddings import EmbeddingService
        from core.retrieval.reranker import BGEReranker, _load_model
        embedding = EmbeddingService()
        reranker = BGEReranker(model=_load_model())
        append(out/'model-startups.jsonl', dict(started_at=datetime.now(timezone.utc).isoformat(),
            seconds=time.perf_counter()-startup, config_sha256=digest(CONFIG)))
        from psycopg.conninfo import make_conninfo
        os.environ['DATABASE_URL'] = make_conninfo(os.environ['DATABASE_URL'], options='-c default_transaction_read_only=on -c statement_timeout=60000')
        rag = RAGService(RetrievalService(embedding_service=embedding, repository=DocumentChunkRepository(), reranker=reranker), provider)
        original = rag.retrieve_contexts
        def retrieve(*args, **kwargs):
            kwargs['document_ids'] = [DOC]
            kwargs['roles'] = CONFIG['roles']
            result = original(*args, **kwargs)
            contexts.extend(result)
            return result
        rag.retrieve_contexts = retrieve
        original_generate = rag.generate_answer
        rag_results = []
        def record_generate(*args, **kwargs):
            result = original_generate(*args, **kwargs)
            rag_results.append(result)
            return result
        rag.generate_answer = record_generate
        agent = KnowledgeAgent(rag)
    else:
        agent = SQLAnalyticsAgent(await create_repository_from_env(), llm=provider, inventory_only=False)
    append(out/'runtime-imports.jsonl', dict(stage='generate', modules=assert_runtime_isolation()))
    cases = json.loads((out/'cases.json').read_text(encoding='utf-8'))[group]
    existing = {r['id'] for r in read_jsonl(out/group/'generations.jsonl')}
    try:
        for case in cases:
            if case['id'] in existing or (ids and case['id'] not in ids):
                continue
            calls.clear(); contexts.clear()
            if group == 'knowledge':
                rag_results.clear()
            start = time.perf_counter()
            row = dict(id=case['id'], question=case['question'])
            try:
                request = AgentRequest(question=case['question'], identity=VerifiedIdentity(subject='frozen-evaluation',
                    permissions={'documents:read','analytics:read'}, document_roles={'employee'}),
                    metadata={'retrieval_method':CONFIG['retrieval_method']})
                result = await agent.run(request)
                row.update(result=result.model_dump(), contexts=list(contexts))
                if group == 'knowledge':
                    metadata = result.metadata
                    blocked = metadata.get('claim_verification',{}).get('status') == 'unavailable'
                    abstained = bool(rag_results[-1].insufficient_context)
                    row.update(abstained=abstained, verifier_block=blocked,
                        citations=citation_audit(result.answer, contexts, case['policy_pages'], abstained or blocked))
            except Exception as error:
                row['generation_error'] = type(error).__name__
            row.update(elapsed_seconds=time.perf_counter()-start, calls=list(calls))
            append_once(out/group/'generations.jsonl', row, ('id',))
            print(json.dumps(dict(stage='generate',group=group,id=case['id'],error=row.get('generation_error'),
                status=row.get('result',{}).get('metadata',{}).get('execution_status'), seconds=round(row['elapsed_seconds'],3))), flush=True)
            if row.get('generation_error') or any(c.get('error_type') in {'RateLimitError','AuthenticationError'} for c in calls):
                break
            await asyncio.sleep(2)
    finally:
        if group == 'knowledge':
            await agent.close()
        else:
            await agent.repository.close()
        provider.close()


async def score(out, group, ids):
    verify(out)
    cases = {c['id']:c for c in json.loads((out/'cases.json').read_text(encoding='utf-8'))[group]}
    path = out/group/'scores.jsonl'
    existing = {(r['id'],r['metric']) for r in read_jsonl(path)}
    metrics = None
    if group == 'knowledge':
        import torch
        torch.set_num_threads(CONFIG['cpu_threads'])
        from evaluation.ragas_judge import build_ragas_metrics, CodexCLIJudge
        class CachedJudge(CodexCLIJudge):
            async def agenerate(self, prompt, response_model):
                key = digest([prompt,response_model.model_json_schema(),CONFIG['judge_model'],CONFIG['judge_reasoning']])
                cache = out/'judge-cache'/f'{key}.json'
                if cache.exists():
                    return response_model.model_validate(json.loads(cache.read_text(encoding='utf-8'))['response'])
                result = await super().agenerate(prompt, response_model)
                immutable_json(cache, dict(prompt=prompt,schema=response_model.model_json_schema(),response=result.model_dump()))
                return result
        metrics = build_ragas_metrics(judge=CachedJudge(model=CONFIG['judge_model'],reasoning_effort=CONFIG['judge_reasoning']))
    append(out/'runtime-imports.jsonl', dict(stage='score', modules=assert_runtime_isolation()))
    for generation in read_jsonl(out/group/'generations.jsonl'):
        identifier = generation['id']
        if ids and identifier not in ids:
            continue
        case = cases[identifier]
        names = ['faithfulness','answer_relevancy','context_precision'] if group=='knowledge' else ['execution_accuracy','numerical_accuracy']
        for name in names:
            if (identifier,name) in existing:
                continue
            row = dict(id=identifier, metric=name, score=None, error=None, not_applicable=False,
                generation_sha256=digest(generation))
            start = time.perf_counter()
            try:
                result = generation.get('result',{})
                if generation.get('generation_error'):
                    row['error']='generation_failed'
                elif group=='invoice':
                    rows, gold = result.get('data',{}).get('rows',[]), case['reference_rows']
                    if name=='execution_accuracy':
                        row['score']=int(result.get('metadata',{}).get('execution_status') in {'executed','executed_empty'} and compare_rows(rows,gold))
                    else:
                        row['score']=sql_numerical_accuracy(rows,gold)
                        row['not_applicable']=row['score'] is None
                elif name=='faithfulness' and (generation.get('abstained') or generation.get('verifier_block')):
                    row['not_applicable']=True
                else:
                    arguments = dict(user_input=case['question'])
                    if name in {'faithfulness','answer_relevancy'}:
                        arguments['response']=result['answer']
                    if name in {'faithfulness','context_precision'}:
                        arguments['retrieved_contexts']=[c['content'] for c in generation['contexts']]
                    if name=='context_precision':
                        arguments['reference']=case['reference']
                    measured = await metrics[name].ascore(**arguments)
                    value = float(measured.value)
                    if not 0 <= value <= 1:
                        raise ValueError('Nonfinite or out-of-range score')
                    row['score']=value
            except Exception as error:
                row.update(error=type(error).__name__,detail=str(error)[-1000:])
            row['elapsed_seconds']=time.perf_counter()-start
            append_once(path,row,('id','metric'))
            print(json.dumps(dict(stage='score',group=group,id=identifier,metric=name,score=row['score'],error=row['error'])),flush=True)
            if row['error'] and any(s in row.get('detail','').lower() for s in ['usage limit','quota','authentication','model is not supported']):
                return


def summarize(out):
    verify(out)
    summary={}
    for group,total in [('knowledge',30),('invoice',10)]:
        generations=read_jsonl(out/group/'generations.jsonl'); scores=read_jsonl(out/group/'scores.jsonl')
        times=sorted(r['elapsed_seconds'] for r in generations)
        metrics={}
        for name in (['faithfulness','answer_relevancy','context_precision'] if group=='knowledge' else ['execution_accuracy','numerical_accuracy']):
            rows=[r for r in scores if r['metric']==name]
            values=[r['score'] for r in rows if r['score'] is not None]
            metrics[name]=dict(mean=statistics.mean(values) if values else None,scored=len(values),
                not_applicable=sum(r['not_applicable'] for r in rows),errors=sum(bool(r['error']) for r in rows),missing=total-len(rows))
        summary[group]=dict(expected=total,attempted=len(generations),missing=total-len(generations),metrics=metrics,
            latency_seconds=dict(p50=statistics.median(times) if times else None,p95=times[min(len(times)-1,int(.95*len(times)))] if times else None),
            llm_calls=sum(len(r.get('calls',[])) for r in generations),generation_errors=sum(bool(r.get('generation_error')) for r in generations))
        if group=='knowledge':
            summary[group].update(abstentions=sum(r.get('abstained',False) for r in generations),
                verifier_blocks=sum(r.get('verifier_block',False) for r in generations),
                valid_citation_questions=sum(r.get('citations',{}).get('citation_validity')==1 for r in generations),
                correct_abstentions=sum(r.get('abstained',False) and int(r['id'][1:])>25 for r in generations),
                supported_abstentions=sum(r.get('abstained',False) and int(r['id'][1:])<=25 for r in generations))
    save(out/'summary.json',summary)
    print(json.dumps(summary,indent=2))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--stage',choices=['freeze','verify','generate','score','summarize','postflight'],required=True)
    parser.add_argument('--group',choices=['knowledge','invoice'],default='knowledge')
    parser.add_argument('--ids',nargs='*')
    parser.add_argument('--env-file',type=Path)
    args=parser.parse_args()
    if args.env_file:
        load_dotenv(args.env_file)
    for key,value in {'GROQ_MODEL':CONFIG['agent_model'],'EMBEDDING_MODEL':CONFIG['embedding_model'],
        'EMBEDDING_BACKEND':'local','RERANKER_MODEL':'bge','RERANKER_QUANTIZE':'int8',
        'KNOWLEDGE_MULTIQUERY_ENABLED':'0','KNOWLEDGE_CLAIM_VERIFICATION_ENABLED':'0','SQL_INVENTORY_ONLY':'false',
        'KNOWLEDGE_CONTEXT_MAX_CHARS':'24000','KNOWLEDGE_COMPLETENESS_RULE':'0',
        'HF_HUB_OFFLINE':'1','OMP_NUM_THREADS':'2','TOKENIZERS_PARALLELISM':'false'}.items():
        os.environ[key]=value
    out=args.output.resolve()
    if args.stage=='freeze': freeze(out)
    elif args.stage=='verify': verify(out); print('Frozen sources, cases and historical artifacts verified.')
    elif args.stage in {'generate','score'}: asyncio.run((generate if args.stage=='generate' else score)(out,args.group,args.ids))
    elif args.stage=='postflight':
        verify(out)
        before=json.loads((out/'database-before.json').read_text(encoding='utf-8'))
        after=database_snapshot()
        immutable_json(out/'database-after.json',after)
        if json.loads(json.dumps(after,default=encode)) != before:
            raise ValueError('Database/corpus snapshot changed; do not present as one fixed-snapshot cohort')
        print('Read-only live data/corpus unchanged; historical artifacts verified.')
    else: summarize(out)


if __name__=='__main__': main()
