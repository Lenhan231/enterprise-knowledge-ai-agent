#!/usr/bin/env python3
"""Fresh reviewed questions: E5 dense30 and three BGE reranking variants on Colab."""
import argparse
import gc
import importlib.metadata
import json
import os
from pathlib import Path
import platform
from time import perf_counter

import numpy as np
import freeze_fresh_review_set as frozen
import evaluate_reranker_source_context as context
import evaluate_vietstyle_reranker as previous
from evaluate_embedding_candidates import summarize_evidence, token_lengths, unit_vectors
from rescore_vietstyle_evidence import check_character_coverage
from core.evaluation.evidence_metrics import score_evidence

ROOT=frozen.ROOT
SNAPSHOT=ROOT/'artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1'
MODEL='intfloat/multilingual-e5-base'
REVISION='d128750597153bb5987e10b1c3493a34e5a4502a'
ARMS=('plain','parent-plain','narrative-parent')
RENDERERS=(lambda rows,i: rows[i]['content'],context.render_parent_plain,context.render_narrative_parent)

def check(ok,msg):
    if not ok:raise ValueError(msg)
def save(path,data): frozen.save(path,data)
def file_sha(path): return frozen.sha(path.read_bytes())

def load_inputs():
    # This is the fresh-set validator, not the historical Q01-Q20 loader.
    frozen.verify(self_check=True)
    if (ROOT/'bundle-manifest.json').exists():
        for name,sha in frozen.read(ROOT/'bundle-manifest.json')['files'].items():
            check(file_sha(ROOT/name)==sha,'Bundle changed: '+name)
    rows,_,_,sources=frozen.source_context()
    cases=frozen.read(frozen.OUT/'cases.json')['cases']; labels=frozen.read(frozen.OUT/'evidence.json')
    folder=SNAPSHOT/'candidates/multilingual-e5-base'
    recipe=frozen.read(folder/'results.json')['configuration']
    check(recipe['model_id']==MODEL and recipe['revision']==REVISION and recipe['query_prefix']=='query: '
          and recipe['passage_prefix']=='passage: ' and recipe['max_sequence_length']==512
          and recipe['normalize_embeddings'] and recipe['dtype']=='float32','Wrong E5 recipe')
    check(frozen.sha(frozen.canonical(frozen.CORPUS))==recipe['corpus_sha256'],'Wrong saved corpus')
    order=frozen.sha(json.dumps([(r['document_id'],r['chunk_index']) for r in rows]).encode())
    check(order==recipe['row_order_sha256'],'Wrong saved document vector order')
    check(file_sha(folder/'vectors.npy')==recipe['vectors_file_sha256'],'Changed document vectors')
    vectors=np.load(folder/'vectors.npy',allow_pickle=False)
    check(vectors.shape==(1063,768) and np.isfinite(vectors).all()
          and np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5),'Invalid document vectors')
    for lang in ('vi','en'):
        check(len({r['document_id'] for r in rows if r['language']==lang})==5,'Expected five competing documents per language')
    rendered=[{arm:render(rows,i) for arm,render in zip(ARMS,RENDERERS)} for i in range(len(rows))]
    provenance={'frozen_manifest_sha256':file_sha(frozen.OUT/'manifest.json'),'cases_sha256':file_sha(frozen.OUT/'cases.json'),
                'labels_sha256':file_sha(frozen.OUT/'evidence.json'),'corpus_sha256_lf':recipe['corpus_sha256'],
                'document_vectors_sha256':recipe['vectors_file_sha256'],'row_order_sha256':order,
                'runner_sha256':file_sha(Path(__file__)),'rendering_code_sha256':file_sha(Path(context.__file__)),
                'scorer_sha256':file_sha(ROOT/'src/core/evaluation/evidence_metrics.py')}
    return dict(rows=rows,cases=cases,labels=labels,sources=sources,vectors=vectors,rendered=rendered,provenance=provenance)

def pools(data,queries):
    check(queries.shape==(48,768) and np.isfinite(queries).all()
          and np.allclose(np.linalg.norm(queries,axis=1),1,atol=1e-5),'Invalid query vectors')
    same={}
    for case,query in zip(data['cases'],queries):
        key=case['query_language'],case['question']
        if key in same:check(np.array_equal(query,same[key]),'Same query differs across target directions')
        same[key]=query
    check(len(same)==24,'Expected 24 distinct query texts')
    return [previous.dense_candidates(data['rows'],data['vectors'],query,case) for case,query in zip(data['cases'],queries)]

def evidence(data,case,indices):
    chunks=[{'text':data['rows'][i]['content'],'metadata':data['rows'][i]['metadata']} for i in indices]
    sources=data['sources'][case['target_language']]
    result=score_evidence(data['labels'],case['intent_id'],case['target_language'],chunks,sources,k=len(chunks))
    check_character_coverage(data['labels'],sources,chunks,result)
    return result

def summarize(data,candidates,matrices):
    records=[]
    for n,(case,indices) in enumerate(zip(data['cases'],candidates)):
        record={**case,'candidate_chunk_ids':[previous.chunk_id(data['rows'][i]) for i in indices],
                'dense_evidence':evidence(data,case,indices[:10]),'candidate_evidence':evidence(data,case,indices)}
        for arm in ARMS:
            values=matrices[arm][n]
            check(values.shape==(30,) and np.isfinite(values).all(),'Incomplete scores')
            order=np.asarray(indices)[np.argsort(-values,kind='stable')].tolist()
            check(order[:10]==previous.rerank_candidates(indices,values),'Independent stable sort differs')
            record[arm+'_ranking']=[previous.chunk_id(data['rows'][i]) for i in order]
            record[arm+'_evidence']=evidence(data,case,order[:10])
        records.append(record)
    summary={}
    for arm,field in [('dense_top10','dense_evidence'),('candidate_pool30','candidate_evidence')]+[(a,a+'_evidence') for a in ARMS]:
        summary[arm]=summarize_evidence([{'direction':r['direction'],'evidence':r[field]} for r in records])
        if arm=='candidate_pool30':
            summary[arm]={d:{k.replace('_at_10','_at_30'):v for k,v in v.items()} for d,v in summary[arm].items()}
    return records,summary

def verify(data,output):
    report=frozen.read(output/'results.json'); config=report['configuration']
    check(config==frozen.read(output/'config.json') and config['status']=='completed'
          and config['provenance']==data['provenance'],'Wrong completion/configuration/provenance')
    check(config['e5_revision']==REVISION and config['reranker_revision']==previous.REVISION
          and config['dtype']=='float32' and config['candidate_k']==30 and config['final_k']==10
          and config['truncated_inputs']==0,'Wrong inference recipe')
    for name,sha in config['output_hashes'].items():check(file_sha(output/name)==sha,'Changed output: '+name)
    check(frozen.read(output/'rendered-inputs.json')==data['rendered'],'Changed rendered inputs')
    queries=np.load(output/'query-vectors.npy',allow_pickle=False)
    candidates=pools(data,queries)
    check(frozen.read(output/'candidate-pools.json')==candidates,'Candidate replay differs')
    matrices={arm:np.load(output/(arm+'-scores.npy'),allow_pickle=False) for arm in ARMS}
    check(all(m.shape==(48,30) and np.isfinite(m).all() for m in matrices.values()),'Bad score matrix')
    for n,indices in enumerate(candidates):
        for j,i in enumerate(indices):
            texts=data['rendered'][i]
            for a in ARMS:
                for b in ARMS:
                    if texts[a]==texts[b]:check(matrices[a][n,j]==matrices[b][n,j],'Identical-input score lineage differs')
    records,summary=summarize(data,candidates,matrices)
    check(records==report['results'] and summary==report['summary'],'Saved ranking/evidence summary replay differs')
    audit={'status':'passed','case_rankings_verified':144,'scores_verified':4320,'dense_pools_replayed':48,
           'independent_character_coverage':'passed','exact_rendering_and_score_lineage':'passed',
           'results_sha256':file_sha(output/'results.json'),'limits':'Offline replay validates artifacts, not independent inference or answer correctness.'}
    save(output/'verification.json',audit);print(json.dumps(audit,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output-dir',type=Path)
    parser.add_argument('--preflight',action='store_true',help='Offline input/label/vector checks; no inference/download')
    parser.add_argument('--tokenizer-preflight',action='store_true',help='Check all pairs with cached tokenizers only')
    parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--allow-download',action='store_true',help='Download pinned models on THIS execution host')
    parser.add_argument('--device',choices=('cpu','cuda'),default='cuda')
    args=parser.parse_args();data=load_inputs()
    texts=list(dict.fromkeys(c['question'] for c in data['cases']))
    changed={arm:sum(r[arm]!=r['plain'] for r in data['rendered']) for arm in ARMS}
    if args.preflight or args.tokenizer_preflight:
        result={'cases':48,'unique_queries':len(texts),'corpus_chunks':1063,'changed_corpus_inputs':changed,'inference_run':False}
        if args.tokenizer_preflight:
            from transformers import AutoTokenizer
            e5=AutoTokenizer.from_pretrained(MODEL,revision=REVISION,local_files_only=True)
            result['max_query_tokens']=max(token_lengths(e5,['query: '+q for q in texts],512))
            tokenizer=AutoTokenizer.from_pretrained('BAAI/bge-reranker-v2-m3',revision=previous.REVISION,local_files_only=True)
            peak=0
            for q in texts:
                for start in range(0,len(data['rendered']),64):
                    pairs=[(q,r[a]) for r in data['rendered'][start:start+64] for a in ARMS]
                    peak=max(peak,max(previous.check_pair_lengths(tokenizer,pairs,1024)))
            result['max_pair_tokens']=peak
        print(json.dumps(result,indent=2));return
    check(args.output_dir is not None,'Specify --output-dir')
    output=args.output_dir.resolve()
    if args.verify_only:verify(data,output);return
    check(not output.exists(),'Preserve outputs; choose a NEW output directory')
    import torch
    from sentence_transformers import SentenceTransformer,CrossEncoder
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer,AutoConfig
    check(args.device!='cuda' or torch.cuda.is_available(),'No GPU assigned; select Colab GPU, no automatic CPU fallback')
    torch.set_num_threads(4);torch.manual_seed(0)
    if args.device=='cuda':torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    output.mkdir(parents=True)
    config={'status':'encoding_queries','provenance':data['provenance'],'e5_model':MODEL,'e5_revision':REVISION,
            'reranker_model':'BAAI/bge-reranker-v2-m3','reranker_revision':previous.REVISION,'device':args.device,
            'gpu_name':torch.cuda.get_device_name(0) if args.device=='cuda' else None,'dtype':'float32','batch_size':4,
            'candidate_k':30,'final_k':10,'max_query_tokens_limit':512,'max_pair_tokens_limit':1024,'context_token_budget':None,
            'changed_corpus_inputs':changed,'torch_version':torch.__version__,'python_version':platform.python_version(),
            'packages':{p:importlib.metadata.version(p) for p in ('sentence-transformers','transformers','huggingface-hub','numpy')},
            'limits':'12 paired intents; assistant-prepared, user-approved; not independent held-out. No translation/hybrid/generation. Context is ranking-only. Shared-score timing is not independent arm latency.'}
    def checkpoint():save(output/'config.json',config)
    checkpoint()
    try:
        model=SentenceTransformer(MODEL,revision=REVISION,device=args.device,local_files_only=not args.allow_download,
                                  model_kwargs={'torch_dtype':torch.float32})
        check(model.max_seq_length>=512,'E5 packaged limit below recipe');model.max_seq_length=512
        queries=['query: '+q for q in texts]
        config['max_observed_query_tokens']=max(token_lengths(model.tokenizer,queries,512))
        started=perf_counter()
        unique=unit_vectors(model.encode(queries,batch_size=2,normalize_embeddings=True,convert_to_numpy=True,prompt='',show_progress_bar=True))
        config['query_encoding_seconds']=perf_counter()-started
        query_vectors=np.asarray([unique[texts.index(c['question'])] for c in data['cases']],dtype=np.float32)
        np.save(output/'query-vectors.npy',query_vectors)
        del model;gc.collect()
        if args.device=='cuda':torch.cuda.empty_cache()
        # Freeze dense pools from vectors/query/access filters before loading the reranker.
        candidates=pools(data,query_vectors);save(output/'candidate-pools.json',candidates)
        save(output/'query-inputs.json',{'texts':queries,'case_ids':[c['id'] for c in data['cases']]})
        save(output/'rendered-inputs.json',data['rendered'])
        model_path=snapshot_download('BAAI/bge-reranker-v2-m3',revision=previous.REVISION,local_files_only=not args.allow_download,
            allow_patterns=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model'])
        tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True)
        architecture=AutoConfig.from_pretrained(model_path,local_files_only=True)
        check(architecture.num_labels==1 and architecture.max_position_embeddings-2>=1024,'Wrong reranker architecture')
        pairs=[(c['question'],data['rendered'][i][a]) for c,indices in zip(data['cases'],candidates) for i in indices for a in ARMS]
        lengths=previous.check_pair_lengths(tokenizer,pairs,1024)
        config.update(max_observed_pair_tokens=max(lengths),truncated_inputs=0,status='reranking');checkpoint()
        model=CrossEncoder(model_path,device=args.device,max_length=1024,model_kwargs={'torch_dtype':torch.float32})
        def predict(values):return np.asarray(model.predict(values,batch_size=4,show_progress_bar=False,activation_fn=torch.nn.Identity(),convert_to_numpy=True),dtype=np.float32).reshape(-1)
        predict(pairs[:1])
        matrices={a:np.full((48,30),np.nan,dtype=np.float32) for a in ARMS};timings=[]
        for n,(case,indices) in enumerate(zip(data['cases'],candidates)):
            if args.device=='cuda':torch.cuda.synchronize()
            started=perf_counter()
            matrices['plain'][n]=predict([(case['question'],data['rendered'][i]['plain']) for i in indices])
            matrices['parent-plain'][n]=matrices['plain'][n]
            delta=[j for j,i in enumerate(indices) if data['rendered'][i]['parent-plain']!=data['rendered'][i]['plain']]
            if delta:matrices['parent-plain'][n,delta]=predict([(case['question'],data['rendered'][indices[j]]['parent-plain']) for j in delta])
            # Narrative inputs are exactly plain tables / predecessor narrative inputs.
            matrices['narrative-parent'][n]=[matrices['plain' if context.is_structured_table(data['rows'][i]) else 'parent-plain'][n,j] for j,i in enumerate(indices)]
            if args.device=='cuda':torch.cuda.synchronize()
            timings.append(perf_counter()-started)
            for a,m in matrices.items():np.save(output/(a+'-scores.npy'),m)
            config.update(cases_completed=n+1,shared_compute_seconds=timings);checkpoint()
            print(f"{n+1}/48 {case['id']} changed_pairs={len(delta)} seconds={timings[-1]:.2f}",flush=True)
        records,summary=summarize(data,candidates,matrices)
        names=['query-vectors.npy','candidate-pools.json','query-inputs.json','rendered-inputs.json']+[a+'-scores.npy' for a in ARMS]
        config.update(status='completed',output_hashes={name:file_sha(output/name) for name in names});checkpoint()
        save(output/'results.json',{'configuration':config,'summary':summary,'results':records})
        verify(data,output)
        print(json.dumps(summary,indent=2))
    except Exception as error:
        config.update(status='failed',error_type=type(error).__name__);checkpoint();raise

if __name__=='__main__':
    os.environ.setdefault('TOKENIZERS_PARALLELISM','false')
    main()