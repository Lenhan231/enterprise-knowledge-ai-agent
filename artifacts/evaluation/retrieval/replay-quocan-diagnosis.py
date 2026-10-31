import sys,os,json,subprocess,hashlib,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
root=Path(__file__).resolve().parents[3];sys.path.insert(0,str(root/'src'))
from dotenv import load_dotenv
load_dotenv(root/'.env')
from core.database.document_chunks_repository import DocumentChunkRepository
from core.embeddings.embedding_service import EmbeddingService
from core.retrieval.methods.common import lexical_tsquery
from core.evaluation.retrieval_metrics import recall_at_k,precision_at_k,reciprocal_rank,ndcg_at_k
ref='6564702c93a028d803c309431e60e447d87bc0c3'
def saved(p):return subprocess.check_output(['git','show',ref+':'+p],cwd=root)
cases_bytes=saved('evaluation/long_hau_2008_cases.json');cases=json.loads(cases_bytes)
old=json.loads(saved('artifacts/benchmark/long_hau_2008.json'))
new=json.loads(saved('artifacts/benchmark/long_hau_2008_huy_retrieval.json'))
repo=DocumentChunkRepository();repo.conn.rollback()
repo.conn.execute('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY')
repo.conn.execute("SET LOCAL statement_timeout='30s'")
rows=repo.conn.execute("SELECT c.id,c.document_name,c.chunk_index,c.content,c.metadata,c.embedding,d.company,d.fiscal_year,d.processing_status,d.allowed_roles FROM document_chunks c LEFT JOIN documents d ON d.document_id=c.metadata->>'document_id' ORDER BY c.id").fetchall()
corpus_hash=hashlib.sha256(json.dumps(rows,ensure_ascii=False,default=lambda x:x.tolist() if hasattr(x,'tolist') else str(x)).encode()).hexdigest()
model_ids={r[4].get('embedding_model') for r in rows}
assert len(model_ids)==1 and None not in model_ids,model_ids
model_id=model_ids.pop();print('Loading query embedding model',model_id,flush=True)
embed=EmbeddingService(model_name=model_id,backend_name='local')
variants={'legacy_dense':None,'dense':('dense',1.0,2.0),'bm25':('bm25',1.0,2.0),'hybrid_1_2':('hybrid',1.0,2.0),'hybrid_1_1':('hybrid',1.0,1.0),'hybrid_2_1':('hybrid',2.0,1.0),'hybrid_4_1':('hybrid',4.0,1.0)}
report={'created_at':datetime.now(timezone.utc).isoformat(),'quocan_commit':subprocess.check_output(['git','rev-parse',ref],cwd=root,text=True).strip(),'retrieval_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),'case_sha256':hashlib.sha256(cases_bytes).hexdigest(),'live_snapshot_sha256':corpus_hash,'corpus_chunks':len(rows),'embedding_model':model_id,'protocol':'Same read-only repeatable-read snapshot, identical query vectors, top-k 10, no company/role filter as in original benchmark; generation not run','results':[]}
oldmap={r['id']:r for r in old['results']};newmap={r['id']:r for r in new['results']}
for case in cases:
 expected=oldmap[case['id']]['expected_chunk_ids'];gold=set(expected)
 # Verify labels and text against the saved artifact, not just page numbers.
 for g in oldmap[case['id']]['gold_evidence']:
  found=[r for r in rows if r[4]['document_id']==g['document_id'] and r[2]==g['chunk_index']]
  assert len(found)==1 and found[0][3]==g['content'],(case['id'],'gold snapshot changed')
 vector=np.asarray(embed.embed_query(case['question']),dtype=np.float32)
 result={'id':case['id'],'question':case['question'],'gold':expected,'lexical_terms':lexical_tsquery(case['question']),'variants':{}}
 for key,options in variants.items():
  if options is None:
   retrieved=repo.conn.execute('SELECT metadata,chunk_index,1-(embedding <=> %s) FROM document_chunks ORDER BY embedding <=> %s,id LIMIT 10',(vector,vector)).fetchall()
   ids=[f"{m['document_id']}::chunk::{i}" for m,i,s in retrieved]
  else:
   method,dw,bw=options
   chunks=repo.similarity_search(vector if method!='bm25' else None,10,query=case['question'],method=method,dense_weight=dw,bm25_weight=bw)
   ids=[f'{c.document_id}::chunk::{c.chunk_index}' for c in chunks]
  result['variants'][key]={'ranked_chunk_ids':ids,'recall@10':recall_at_k(gold,ids,10),'precision@10':precision_at_k(gold,ids,10),'mrr':reciprocal_rank(gold,ids),'ndcg@10':ndcg_at_k(gold,ids,10)}
 result['legacy_saved_ranking_matches']=result['variants']['legacy_dense']['ranked_chunk_ids']==[c['chunk_id'] for c in oldmap[case['id']]['retrieved_contexts']]
 result['hybrid_saved_ranking_matches']=result['variants']['hybrid_1_2']['ranked_chunk_ids']==[c['chunk_id'] for c in newmap[case['id']]['retrieved_contexts']]
 report['results'].append(result);print(case['id'],'completed',flush=True)
repo.close()
report['aggregates']={}
for label,start,end in [('all',1,24),('pvfcco',1,12),('long_hau',13,22),('cross_document',23,24)]:
 selected=[r for r in report['results'] if start<=int(r['id'][1:])<=end]
 report['aggregates'][label]={key:{m:round(sum(r['variants'][key][m] for r in selected)/len(selected),4) for m in ('recall@10','precision@10','mrr','ndcg@10')} for key in variants}
report['saved_ranking_matches']={k:sum(r[k] for r in report['results']) for k in ('legacy_saved_ranking_matches','hybrid_saved_ranking_matches')}
p=root/'artifacts/evaluation/retrieval/quocan-diagnosis-20261014.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'output':str(p),'aggregates':report['aggregates'],'saved_ranking_matches':report['saved_ranking_matches']},indent=2),flush=True)