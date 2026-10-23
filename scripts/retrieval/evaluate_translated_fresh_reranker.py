#!/usr/bin/env python3
"""Paired dense30 vs production translated-hybrid30, same plain BGE final10."""
import argparse
import importlib.metadata
import platform
import json
import os
from pathlib import Path
from time import perf_counter
import numpy as np
import evaluate_fresh_reviewed_reranker as base
from fresh_translated_candidates import build_candidates

ROOT=base.ROOT
INPUT=ROOT/'artifacts/evaluation/colab-translated-hybrid-fresh-v1'
BASELINE=ROOT/'artifacts/evaluation/colab-fresh-reviewed-v1/colab-results'
ARMS=('dense','translated_hybrid')

def load():
    data=base.load_inputs();base.verify(data,BASELINE)
    info=base.frozen.read(INPUT/'candidate-inputs.json')
    base.check(info['frozen_provenance']==data['provenance'] and info['baseline_results_sha256']==base.file_sha(BASELINE/'results.json'),'Wrong baseline/frozen inputs')
    for name,field in [('translations.json','translations_sha256'),('lexical-inputs.json','lexical_inputs_sha256')]:
        base.check(base.file_sha(INPUT/name)==info[field],'Changed '+name)
    base.check(base.file_sha(ROOT/'src/core/retrieval/methods/translated_hybrid.py')==info['production_method_sha256'],'Changed production fusion')
    base.check(base.file_sha(Path(__file__).with_name('fresh_translated_candidates.py'))==info['adapter_sha256'],'Changed corpus adapter')
    translations=base.frozen.read(INPUT/'translations.json');lexical=base.frozen.read(INPUT/'lexical-inputs.json')
    from core.retrieval.methods.common import explicit_fiscal_year
    base.check(not any(explicit_fiscal_year(q) for r in translations['records'] if r['queries'] for q in r['queries'].values()),'Fiscal-year prioritization needs an explicit adapter; not supported in this frozen set')
    queries=np.load(BASELINE/'query-vectors.npy',allow_pickle=False)
    dense=base.pools(data,queries)
    hybrid,details=build_candidates(data['rows'],data['vectors'],queries,data['cases'],lexical['document_terms'],lexical['query_terms'],translations)
    base.check(hybrid==info['pools'] and details==info['details'],'Hybrid candidate replay differs')
    data.update(candidates={'dense':dense,'translated_hybrid':hybrid},candidate_info=info,
                translated_provenance={'frozen':data['provenance'],'candidate_inputs_sha256':base.file_sha(INPUT/'candidate-inputs.json'),
                    'baseline_results_sha256':base.file_sha(BASELINE/'results.json'),'translation_inputs_sha256':info['translations_sha256'],
                    'lexical_inputs_sha256':info['lexical_inputs_sha256'],'runner_sha256':base.file_sha(Path(__file__))})
    return data

def summarize(data,matrices):
    records=[]
    old=base.frozen.read(BASELINE/'results.json')['results']
    for n,case in enumerate(data['cases']):
        record={**case,'raw_dense_evidence':base.evidence(data,case,data['candidates']['dense'][n][:10])}
        for arm in ARMS:
            indices=data['candidates'][arm][n];values=matrices[arm][n]
            base.check(values.shape==(30,) and np.isfinite(values).all(),'Incomplete logits')
            ranked=np.asarray(indices)[np.argsort(-values,kind='stable')].tolist()
            base.check(ranked[:10]==base.previous.rerank_candidates(indices,values),'Stable sort mismatch')
            record[arm+'_candidates']=[base.previous.chunk_id(data['rows'][i]) for i in indices]
            record[arm+'_ranking']=[base.previous.chunk_id(data['rows'][i]) for i in ranked]
            record[arm+'_candidate_evidence']=base.evidence(data,case,indices)
            record[arm+'_evidence']=base.evidence(data,case,ranked[:10])
        record['dense_baseline_matches_previous']=record['raw_dense_evidence']==old[n]['dense_evidence']
        record['plain_control_matches_previous']=[(r['id'],r['complete']) for r in record['dense_evidence']['requirements']]==[(r['id'],r['complete']) for r in old[n]['plain_evidence']['requirements']]
        records.append(record)
    summary={}
    for arm,field in [('dense_top10','raw_dense_evidence')]+[(a,a+'_evidence') for a in ARMS]+[(a+'_candidate30',a+'_candidate_evidence') for a in ARMS]:
        summary[arm]=base.summarize_evidence([{'direction':r['direction'],'evidence':r[field]} for r in records])
        if arm.endswith('candidate30'):summary[arm]={d:{k.replace('_at_10','_at_30'):v for k,v in s.items()} for d,s in summary[arm].items()}
    return records,summary

def verify(data,out):
    report=base.frozen.read(out/'results.json');config=report['configuration']
    base.check(config==base.frozen.read(out/'config.json') and config['status']=='completed' and config['provenance']==data['translated_provenance'],'Changed configuration/inputs')
    base.check(config['revision']==base.previous.REVISION and config['dtype']=='float32' and config['truncated_inputs']==0 and config['candidate_k']==30 and config['final_k']==10,'Wrong inference settings')
    base.check(set(config['output_hashes'])=={a+'-scores.npy' for a in ARMS},'Missing score hashes')
    for name,sha in config['output_hashes'].items():base.check(base.file_sha(out/name)==sha,'Changed '+name)
    matrices={a:np.load(out/(a+'-scores.npy'),allow_pickle=False) for a in ARMS}
    base.check(all(m.shape==(48,30) for m in matrices.values()),'Wrong matrix shape')
    for n in range(48):
        a,b=[data['candidates'][arm][n] for arm in ARMS]
        for i in set(a)&set(b):base.check(matrices['dense'][n,a.index(i)]==matrices['translated_hybrid'][n,b.index(i)],'Shared input score mismatch')
    records,summary=summarize(data,matrices)
    base.check(records==report['results'] and summary==report['summary'],'Ranking/evidence replay differs')
    audit={'status':'passed','cases':48,'paired_rankings':96,'score_entries':2880,'hybrid_candidate_replay':'passed','shared_input_lineage':'passed','independent_character_coverage':'passed','results_sha256':base.file_sha(out/'results.json')}
    base.save(out/'verification.json',audit);print(json.dumps(audit,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--preflight',action='store_true');parser.add_argument('--verify-only',action='store_true')
    parser.add_argument('--output-dir',type=Path);parser.add_argument('--allow-download',action='store_true')
    args=parser.parse_args();data=load()
    if args.preflight:
        print(json.dumps({'status':'passed','cases':48,'reranker_candidates':30,'branch_candidates':300,'translation_model':base.frozen.read(INPUT/'translations.json')['model'],'translation_failures':data['candidate_info']['failed_translations'],'inference_run':False},indent=2));return
    base.check(args.output_dir is not None,'Specify --output-dir');out=args.output_dir.resolve()
    if args.verify_only:verify(data,out);return
    base.check(not out.exists(),'Preserve previous outputs; choose a NEW output directory')
    import torch
    from sentence_transformers import CrossEncoder
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer,AutoConfig
    base.check(torch.cuda.is_available(),'No Colab GPU; no CPU fallback')
    torch.set_num_threads(4);torch.manual_seed(0);torch.backends.cuda.matmul.allow_tf32=False;torch.backends.cudnn.allow_tf32=False
    model_path=snapshot_download('BAAI/bge-reranker-v2-m3',revision=base.previous.REVISION,local_files_only=not args.allow_download,
        allow_patterns=['config.json','model.safetensors','tokenizer.json','tokenizer_config.json','special_tokens_map.json','sentencepiece.bpe.model'])
    tokenizer=AutoTokenizer.from_pretrained(model_path,local_files_only=True)
    architecture=AutoConfig.from_pretrained(model_path,local_files_only=True)
    base.check(architecture.num_labels==1 and architecture.max_position_embeddings-2>=1024,'Wrong BGE architecture')
    unions=[list(dict.fromkeys(data['candidates']['dense'][n]+data['candidates']['translated_hybrid'][n])) for n in range(48)]
    pairs=[(c['question'],data['rows'][i]['content']) for c,indices in zip(data['cases'],unions) for i in indices]
    lengths=base.previous.check_pair_lengths(tokenizer,pairs,1024)
    out.mkdir(parents=True)
    config={'status':'running','provenance':data['translated_provenance'],'model':'BAAI/bge-reranker-v2-m3','revision':base.previous.REVISION,
            'dtype':'float32','batch_size':4,'gpu_name':torch.cuda.get_device_name(0),'torch_version':torch.__version__,'python_version':platform.python_version(),
            'packages':{p:importlib.metadata.version(p) for p in ('sentence-transformers','transformers','huggingface-hub','numpy','openai','pydantic')},
            'candidate_k':30,'branch_candidate_k':300,'final_k':10,'truncated_inputs':0,'max_observed_pair_tokens':max(lengths),
            'context_token_budget':None,'translation_model':base.frozen.read(INPUT/'translations.json')['model'],
            'translation_failures':data['candidate_info']['failed_translations'],'limits':'Same-run dense/plain control vs translated-hybrid/plain. No extra context or generation. Stable frozen chunk-ID BM25 tie break replaces database UUIDs. Translations and E5 vectors reused from frozen preparations. Shared compute is not independent arm latency.'}
    def checkpoint():base.save(out/'config.json',config)
    checkpoint()
    try:
        model=CrossEncoder(model_path,device='cuda',max_length=1024,model_kwargs={'torch_dtype':torch.float32})
        def predict(values):return np.asarray(model.predict(values,batch_size=4,show_progress_bar=False,activation_fn=torch.nn.Identity(),convert_to_numpy=True),dtype=np.float32).reshape(-1)
        predict(pairs[:1]);matrices={a:np.full((48,30),np.nan,dtype=np.float32) for a in ARMS};times=[]
        for n,(case,indices) in enumerate(zip(data['cases'],unions)):
            torch.cuda.synchronize();start=perf_counter()
            scores=predict([(case['question'],data['rows'][i]['content']) for i in indices]);lookup=dict(zip(indices,scores))
            for a in ARMS:matrices[a][n]=[lookup[i] for i in data['candidates'][a][n]]
            torch.cuda.synchronize();times.append(perf_counter()-start)
            for a,m in matrices.items():np.save(out/(a+'-scores.npy'),m)
            config.update(cases_completed=n+1,shared_compute_seconds=times);checkpoint()
            print(f"{n+1}/48 {case['id']} unique_pairs={len(indices)}",flush=True)
        records,summary=summarize(data,matrices)
        config.update(status='completed',output_hashes={a+'-scores.npy':base.file_sha(out/(a+'-scores.npy')) for a in ARMS});checkpoint()
        base.save(out/'results.json',{'configuration':config,'summary':summary,'results':records});verify(data,out)
        print(json.dumps(summary,indent=2))
    except Exception as error:
        config.update(status='failed',error_type=type(error).__name__);checkpoint();raise

if __name__=='__main__':
    os.environ.setdefault('TOKENIZERS_PARALLELISM','false');main()