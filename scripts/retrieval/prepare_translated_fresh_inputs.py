#!/usr/bin/env python3
"""Prepare approved automatic translations and exact PG lexemes; no DB writes."""
import argparse
import os
from pathlib import Path
from time import perf_counter,sleep
import numpy as np
from dotenv import load_dotenv
import evaluate_fresh_reviewed_reranker as base
from fresh_translated_candidates import bm25_scores,build_candidates
from core.retrieval.methods.common import lexical_tsquery
from core.retrieval.methods.bm25 import BM25_CTES
from core.retrieval.query_translator import QueryTranslator
from core.llm.groq_provider import GroqProvider
from core.database.connection_limit import connect_database,close_database_connection

ROOT=base.ROOT
OUT=ROOT/'artifacts/evaluation/colab-translated-hybrid-fresh-v1'
BASELINE=ROOT/'artifacts/evaluation/colab-fresh-reviewed-v1/colab-results'
LEXEMES_SQL="""SELECT d.ordinality-1, coalesce((SELECT jsonb_object_agg(t.lexeme,cardinality(t.positions))
 FROM unnest(to_tsvector('simple',d.text)) AS t(lexeme,positions,weights)), '{}'::jsonb)
 FROM unnest(%s::text[]) WITH ORDINALITY AS d(text,ordinality) ORDER BY d.ordinality"""

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--allow-groq',action='store_true',help='Send ONLY 24 question texts to Groq; requires user consent')
    args=parser.parse_args()
    base.check(args.allow_groq,'Explicit --allow-groq required; no API call made')
    load_dotenv(ROOT/'.env')
    data=base.load_inputs();base.verify(data,BASELINE)
    OUT.mkdir(exist_ok=True)
    base.check(not (OUT/'candidate-inputs.json').exists(),'Inputs already frozen; preserve them')
    previous=base.frozen.read(OUT/'translations.json') if (OUT/'translations.json').exists() else None
    llm=GroqProvider();translator=QueryTranslator(llm)
    records=previous['records'] if previous else []
    if previous:base.check(previous['model']==llm.model_name,'Do not mix translation models')
    texts=list(dict.fromkeys(c['question'] for c in data['cases']))
    try:
        for question in texts:
            if any(r['question']==question for r in records):continue
            started=perf_counter();llm.last_usage=None
            try:queries=translator.translate(question,'auto');error=None
            except Exception as exc:queries=None;error=type(exc).__name__
            records.append({'question':question,'queries':queries,'error':error,'api_seconds':perf_counter()-started,'usage':llm.last_usage})
            base.save(OUT/'translations.json',{'status':'preparing' if len(records)<24 else 'completed','model':llm.model_name,
                'source_language_mode':'auto','external_api_consent':'User explicitly approved sending these 24 simulated question texts to Groq in chat 2026-10-21.',
                'translator_sha256':base.file_sha(ROOT/'src/core/retrieval/query_translator.py'),
                'translation_prompt_sha256':base.file_sha(ROOT/'src/core/prompts/translation.py'),
                'questions_sha256':base.file_sha(base.frozen.OUT/'cases.json'),'records':records})
            print(f'Translation {len(records)}/24: '+('ok' if error is None else error),flush=True)
            sleep(2)
    finally:llm.close()
    translation=base.frozen.read(OUT/'translations.json')
    base.check(len(records)==24,'Incomplete translations')
    successful=sum(r['error'] is None for r in records)
    base.check(successful>0,'No successful translations; no meaningful translated benchmark prepared')
    conn=connect_database(os.environ['DATABASE_URL'])
    try:
        conn.execute('BEGIN READ ONLY');conn.execute("SET LOCAL statement_timeout='60s'")
        readonly,version=conn.execute("SELECT current_setting('transaction_read_only'),version()").fetchone()
        base.check(readonly=='on','Expected read-only SQL')
        terms=[row[1] for row in conn.execute(LEXEMES_SQL,([r['content'] for r in data['rows']],)).fetchall()]
        query_texts=list(dict.fromkeys(texts+[q for r in records if r['queries'] for q in r['queries'].values()]))
        query_tokens=conn.execute(LEXEMES_SQL,([lexical_tsquery(q) for q in query_texts],)).fetchall()
        query_terms={q:list(row[1]) for q,row in zip(query_texts,query_tokens)}
        parity=[]
        for lang,question in [('vi',texts[0]),('en',texts[1])]:
            indices=[i for i,r in enumerate(data['rows']) if r['language']==lang]
            sql="WITH eligible AS MATERIALIZED (SELECT e.ordinality::bigint AS id,false AS year_match,to_tsvector('simple',e.text) AS document_vector FROM unnest(%s::text[]) WITH ORDINALITY AS e(text,ordinality)),"+BM25_CTES+' SELECT id,bm25_score FROM bm25_scores ORDER BY id'
            actual={indices[i-1]:float(score) for i,score in conn.execute(sql,([data['rows'][i]['content'] for i in indices],lexical_tsquery(question))).fetchall()}
            expected=dict(bm25_scores(indices,terms,query_terms[question]))
            base.check(set(actual)==set(expected) and all(np.isclose(actual[i],expected[i],rtol=1e-10,atol=1e-10) for i in actual),'SQL/Python BM25 mismatch')
            parity.append({'language':lang,'scores_verified':len(actual)})
        conn.rollback()
    finally:close_database_connection(conn)
    base.save(OUT/'lexical-inputs.json',{'tokenizer':"PostgreSQL to_tsvector('simple')",'query_cleanup':'production lexical_tsquery','postgres_version':version,
        'readonly_transaction':True,'document_terms':terms,'query_terms':query_terms,'sql_formula_parity':parity,
        'limits':'Production SQL BM25 formula/lexemes, target/ACL corpus statistics. Stable chunk-ID tie break replaces unavailable live DB row UUIDs.'})
    queries=np.load(BASELINE/'query-vectors.npy',allow_pickle=False)
    pools,details=build_candidates(data['rows'],data['vectors'],queries,data['cases'],terms,query_terms,translation)
    base.save(OUT/'candidate-inputs.json',{'status':'frozen_before_reranking','baseline_results_sha256':base.file_sha(BASELINE/'results.json'),
        'frozen_provenance':data['provenance'],'translations_sha256':base.file_sha(OUT/'translations.json'),
        'lexical_inputs_sha256':base.file_sha(OUT/'lexical-inputs.json'),'production_method_sha256':base.file_sha(ROOT/'src/core/retrieval/methods/translated_hybrid.py'),
        'adapter_sha256':base.file_sha(Path(__file__).with_name('fresh_translated_candidates.py')),
        'candidate_k':30,'branch_candidate_k':300,'rrf_k':60,'weights':{'dense':1,'bm25':2},'query_language':'auto',
        'document_language_mapping':'verified frozen corpus language; en/vn converted from en/vi; not database attributes',
        'successful_translations':successful,'failed_translations':24-successful,'pools':pools,'details':details})
    print({'status':'candidate_inputs_frozen','translations_ok':successful,'translation_failures':24-successful,'cases':48,'reranker_candidates':30,'branch_candidates':300,'evidence_modified':False,'database_writes':False},flush=True)

if __name__=='__main__':main()
