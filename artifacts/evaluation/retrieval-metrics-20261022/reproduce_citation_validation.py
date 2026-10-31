from pathlib import Path
import sys,json
from types import SimpleNamespace
from unittest.mock import patch
p=Path(__file__).resolve().parents[3];sys.path.insert(0,str(p/'src'))
from core.rag.rag_service import RAGService
contexts=[{'document_name':'first.txt','chunk_index':0,'content':'x'*6000,'metadata':{},'retrieval_method':'hybrid','retrieval_score':0.0,'source_id':'S1'},
          {'document_name':'second.txt','chunk_index':1,'content':'gold','metadata':{},'retrieval_method':'hybrid','retrieval_score':0.0,'source_id':'S2'}]
with patch('core.rag.rag_service.MAX_CONTEXT_CHARS',5000),patch('core.rag.rag_service.generate_with_provider_fallback',return_value=('Synthetic answer [S2]','mock')),patch('core.rag.rag_service.accumulate_token_usage',return_value=None),patch('core.rag.rag_service._get_cached_response',return_value=None),patch('core.rag.rag_service._cache_response'):
 result=RAGService(SimpleNamespace(),SimpleNamespace(model_name='offline-citation-probe')).generate_answer('Question?',roles=['admin'],retrieved_contexts=contexts)
report={'probe':'synthetic generation response cites a source removed by context cap','external_api_calls':False,'llm_inference':False,'cap_chars':5000,'input_source_ids':['S1','S2'],'delivered_source_ids':[x['source_id'] for x in result.contexts],'accepted_answer_source_ids':result.source_ids,'answer':result.answer,'dangling_citation_accepted':bool(set(result.source_ids)-{x['source_id'] for x in result.contexts}),'scope':'Controlled code-path diagnostic; not a measured real-LLM failure rate. No production code changed.'}
(p/'artifacts/evaluation/retrieval-metrics-20261022/citation-validation-probe.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(report,indent=2))
