"""Frozen-corpus adapter for the real translated_hybrid.search; no labels in ranking."""
from collections import Counter
from math import log
from types import SimpleNamespace
import numpy as np
from core.retrieval.methods import translated_hybrid
from core.retrieval.retrieval import RetrievedChunk,RetrievalRequest,make_chunk_id


def bm25_scores(indices,terms,query_terms):
    """Same k1=1.2/b=.75/log-IDF as production SQL, on PostgreSQL simple lexemes."""
    if not indices:return []
    lengths={i:sum(terms[i].values()) for i in indices}
    average=sum(lengths.values())/len(indices)
    if not average:return []
    frequencies=Counter(term for i in indices for term in terms[i])
    query=set(query_terms);result=[]
    for i in indices:
        score=sum(log(1+(len(indices)-frequencies[t]+.5)/(frequencies[t]+.5))
                  *(tf*2.2)/(tf+1.2*(.25+.75*lengths[i]/average))
                  for t,tf in terms[i].items() if t in query)
        if score>0:result.append((i,score))
    return result

class FrozenRepository:
    def __init__(self,rows,vectors,terms,query_terms):
        self.rows,self.vectors,self.terms,self.query_terms=rows,vectors,terms,query_terms
    def similarity_search(self,vector,limit,*,query,method,roles=None,document_ids=None,company=None,metadata_filter=None):
        if company is not None or metadata_filter:raise ValueError('Unsupported extra benchmark filters')
        ids=set(document_ids) if document_ids is not None else None
        eligible=[i for i,r in enumerate(self.rows) if (ids is None or r['document_id'] in ids)
                  and (roles is None or 'admin' in roles or set(roles).intersection(r['allowed_roles'] or []))]
        if not eligible:return []
        if method=='dense':
            scores=self.vectors[eligible]@vector
            ranked=sorted(zip(eligible,map(float,scores)),key=lambda x:-x[1])
        elif method=='bm25':
            ranked=sorted(bm25_scores(eligible,self.terms,self.query_terms[query]),
                          key=lambda x:(-x[1],make_chunk_id(self.rows[x[0]]['document_id'],self.rows[x[0]]['chunk_index'])))
        else:raise ValueError('Expected dense or bm25')
        return [RetrievedChunk(document_name=self.rows[i]['document_name'],chunk_index=self.rows[i]['chunk_index'],
                    content=self.rows[i]['content'],metadata=self.rows[i]['metadata'],retrieval_score=score) for i,score in ranked[:limit]]

class SavedTranslator:
    def __init__(self,records,model):self.records=records;self.llm=SimpleNamespace(model_name=model)
    def translate(self,query,source_lang='auto'):
        if source_lang!='auto':raise ValueError('Benchmark uses production auto language detection')
        row=self.records[query]
        if row['error']:raise RuntimeError('Recorded translation failure')
        return row['queries']


def build_candidates(rows,vectors,queries,cases,terms,query_terms,translation):
    repository=FrozenRepository(rows,vectors,terms,query_terms)
    translator=SavedTranslator({r['question']:r for r in translation['records']},translation['model'])
    language_map={r['document_id']:('vn' if r['language']=='vi' else 'en') for r in rows}
    byid={make_chunk_id(r['document_id'],r['chunk_index']):i for i,r in enumerate(rows)}
    pools=[];details=[]
    for case,query in zip(cases,queries):
        scope=sorted({r['document_id'] for r in rows if r['language']==case['target_language']})
        chunks,info=translated_hybrid.search(repository,query,RetrievalRequest(query=case['question'],top_k=30),
                lambda:translator,roles=case['allowed_roles'],document_ids=scope,
                document_languages={doc:language_map[doc] for doc in scope},query_language='auto')
        if len(chunks)!=30:raise ValueError('Expected 30 hybrid candidates')
        # API latency happened during preparation, not this cached lookup.
        info.pop('translation_latency_ms',None)
        pools.append([byid[make_chunk_id(c.document_id,c.chunk_index)] for c in chunks])
        details.append({'case_id':case['id'],'retrieval_details':info})
    return pools,details