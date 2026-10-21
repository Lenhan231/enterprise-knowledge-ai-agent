#!/usr/bin/env python3
"""Bundle frozen translated-hybrid candidates for a same-run Colab control comparison."""
import ast
import hashlib
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import zipfile
from prepare_fresh_reviewed_colab import cell

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/evaluation/colab-translated-hybrid-fresh-v1'
BASELINE=ROOT/'artifacts/evaluation/colab-fresh-reviewed-v1/colab-results'

def main():
    target=OUT/'translated_fresh_colab_inputs.zip'
    if target.exists():raise ValueError('Bundle already prepared; preserve it')
    original=ROOT/'artifacts/evaluation/colab-fresh-reviewed-v1/fresh_reviewed_colab_inputs.zip'
    with zipfile.ZipFile(original) as z:blobs={n:z.read(n) for n in z.namelist() if n!='bundle-manifest.json'}
    names=['scripts/retrieval/fresh_translated_candidates.py','scripts/retrieval/evaluate_translated_fresh_reranker.py',
           'src/core/retrieval/retrieval.py','src/core/retrieval/methods/translated_hybrid.py',
           'src/core/retrieval/methods/common.py','src/core/retrieval/methods/bm25.py',
           'src/core/retrieval/query_translator.py','src/core/llm/llm_interface.py','src/core/llm/groq_provider.py']
    names += [(OUT/p).relative_to(ROOT).as_posix() for p in ('translations.json','lexical-inputs.json','candidate-inputs.json')]
    config=json.loads((BASELINE/'config.json').read_text())
    names += [(BASELINE/p).relative_to(ROOT).as_posix() for p in ['config.json','results.json',*config['output_hashes']]]
    for name in names:blobs[name]=(ROOT/name).read_bytes()
    for name,b in blobs.items():
        assert '.env' not in Path(name).parts and not name.endswith(('.safetensors','.bin'))
        if name.endswith('.py'):ast.parse(b.decode(),filename=name)
    manifest={'dataset':'translated-hybrid-fresh-v1','status':'prepared_not_run','files':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(blobs.items())},'credentials_included':False,'new_inference_required':'BGE reranker only; original E5 query/document vectors and approved Groq translations are already frozen.'}
    blobs['bundle-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(blobs.items()):z.writestr(n,b)
    with zipfile.ZipFile(target) as z:assert z.testzip() is None
    extra='openai=='+importlib.metadata.version('openai')+' pydantic=='+importlib.metadata.version('pydantic')
    (OUT/'extra-requirements.txt').write_text(extra.replace(' ','\n')+'\n')
    cells=[cell('markdown','''# Translated-hybrid vs dense candidates — fresh frozen evidence v1

48 cases,12 paired intents. Questions/labels/corpus unchanged. Existing E5 document AND query vectors reused.
Automatic translations were made once with the existing Groq gpt-oss-20b QueryTranslator (auto language detection),
with explicit user consent. All24 succeeded. No API key or database access is needed on Colab.

Production translated_hybrid.search is reused through a frozen-corpus adapter: original-query dense,
language-matched BM25 from original/automatic-translated queries, RRF k60, weights dense1/lexical2.
Verified document languages come from the frozen snapshot. Internal branch budget300 (production top_k*10),
fused reranker candidates30, final10. PostgreSQL simple lexemes/production cleanup/formula are replayed offline;
BM25 score parity passed, but stable chunk-ID tie breaks replace unavailable live DB UUIDs.

Both dense/plain and translated-hybrid/plain are reranked AGAIN on this same Colab GPU, FP32/pinned BGE.
Shared candidate-query inputs are scored once with exact lineage. Historical control agreement is diagnostic.
No predecessor context, translation of passages, answer generation, production change or label tuning.
Report BOTH candidate30 availability and final10 evidence, plus regressions. This is development data, not held-out proof.
'''),cell('code',f'%pip -q install sentence-transformers==6.0.1 transformers==5.17.0 huggingface-hub==1.31.0 numpy==2.4.6 python-dotenv {extra}\n'),
    cell('code',"""import os
os.environ.update(OMP_NUM_THREADS='4',MKL_NUM_THREADS='4',TOKENIZERS_PARALLELISM='false',HF_HUB_DISABLE_XET='1')
import torch
assert torch.cuda.is_available(), 'Select GPU runtime.'
print(torch.__version__,torch.cuda.get_device_name(0))
"""),cell('code',"""from google.colab import files
from pathlib import Path
import zipfile
uploaded=files.upload()  # Select translated_fresh_colab_inputs.zip.
assert 'translated_fresh_colab_inputs.zip' in uploaded
work=Path('/content/translated_fresh_experiment')
assert not work.exists(), 'Already extracted: continue below or choose a new directory.'
work.mkdir()
with zipfile.ZipFile('translated_fresh_colab_inputs.zip') as z:
    assert all((work/n).resolve().is_relative_to(work.resolve()) for n in z.namelist())
    z.extractall(work)
del uploaded
os.chdir(work)
"""),cell('code',"""import sys,subprocess
runner=[sys.executable,'scripts/retrieval/evaluate_translated_fresh_reranker.py']
subprocess.run(runner+['--preflight'],check=True)
"""),cell('code',"""output=Path('/content/translated_fresh_results')
# Reuses cached BGE weights if available. No Groq key, DB or E5 query inference needed.
subprocess.run(runner+['--output-dir',str(output),'--allow-download'],check=True)
"""),cell('code',"""subprocess.run(runner+['--output-dir',str(output),'--verify-only'],check=True)
import json
report=json.loads((output/'results.json').read_text())
print('Direction | Dense+rerank | Translated-hybrid+rerank | Dense pool30 | Hybrid pool30')
for d in ('vi->vi','en->en','vi->en','en->vi'):
    counts=[]
    for a in ('dense','translated_hybrid'):
        s=report['summary'][a][d];counts.append(f"{s['full_evidence_cases_at_10']}/{s['full_intent_eligible_cases']}")
    for a in ('dense_candidate30','translated_hybrid_candidate30'):
        s=report['summary'][a][d];counts.append(f"{s['full_evidence_cases_at_30']}/{s['full_intent_eligible_cases']}")
    print(d,*counts,sep=' | ')
"""),cell('code',"""import shutil
archive=shutil.make_archive('/content/translated_fresh_results','zip',root_dir=output)
files.download(archive)
# Return this ZIP to Codex. Partial/failed outputs are not completed benchmark results.
""")]
    for c in cells:
        if c['cell_type']=='code':ast.parse(''.join(l for l in c['source'] if not l.startswith('%')))
    (OUT/'translated_fresh_colab.ipynb').write_text(json.dumps({'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','name':'python3','language':'python'},'accelerator':'GPU'},'cells':cells},indent=2)+'\n')
    (OUT/'README.md').write_text('''# Translated hybrid / plain reranker comparison

Status: automatic translations and candidates prepared; Colab reranking NOT run yet. Evidence remains fresh-reviewed-v1 with the original manifest hash c8f9dae06fd70e9e897912aa4a0a7488e98993c88af2b182a1406db72c51f6f3. All24 Groq translations succeeded with auto language detection. No gold bilingual counterparts were supplied as translations. Approved by user in chat before external API calls. API records/usage are in translations.json; source documents, labels and credentials were not translation inputs.

The existing production translated_hybrid.search handles rank fusion and language routing, through a frozen-corpus repository. E5 original query/document vectors are unchanged. Each arm reranks30 and returns10 with the same plain BGE model. Production hybrid internally takes top_k*10=300 per dense/lexical branch before fusion; this is distinct from the30 candidates delivered to reranking. RRF60, dense1/BM252, equal EN/VN lexical fusion. Five verified target-language documents compete in each case; admin scope, no gold-source filter. The out-of-target-language BM25 scope is empty, as required by the fixed directional experiment.

PostgreSQL simple lexemes were extracted in a read-only transaction over supplied frozen strings, without reading/writing document tables. Python scoring uses production BM25 constants, corpus-local statistics and query cleanup; two SQL numeric parity checks passed. Offline BM25 uses stable chunk-ID ties rather than unavailable original live database row UUIDs. This is a documented offline adapter difference, not a claim of bit-identical live SQL ordering. Fiscal-year prioritization is irrelevant for these frozen queries (none requests an explicit fiscal year).

Run via the supplied notebook, or in the Colab remote VS Code terminal:

    cd /content
    unzip -q translated_fresh_colab_inputs.zip -d translated_fresh_experiment
    cd translated_fresh_experiment
    python -m pip install -r artifacts/evaluation/colab-translated-hybrid-fresh-v1/extra-requirements.txt
    OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false HF_HUB_DISABLE_XET=1 python -u scripts/retrieval/evaluate_translated_fresh_reranker.py --output-dir /content/translated_fresh_results --allow-download

Base sentence-transformers/transformers dependencies are the same versions as the previous Colab run; notebook includes full install. extra-requirements.txt adds only OpenAI SDK/Pydantic for importing the existing production contracts; no API key or external translation request occurs on Colab. Reuse the existing GPU runtime/cache if still available. Both control and treatment reranker logits are computed NEW on this same runtime, with shared-input reuse. Old control results are only checked diagnostically; no cross-run score mixing. Record GPU/software and shared compute timings; those are not independent per-arm/end-to-end latency.

Verify:

    python scripts/retrieval/evaluate_translated_fresh_reranker.py --output-dir /content/translated_fresh_results --verify-only

Download that results folder/ZIP and return for paired gains/losses, pool availability, F03/F08 and all regressions review. Verification must use the EXACT matching extracted input bundle. Inputs are frozen before BGE scores; do not edit labels, translations or candidate rules after seeing results. This is a follow-up on development data, not independent held-out validation or answer accuracy. Production, database records, model vectors, questions and evidence are unchanged. The accidental word run in frozen REVIEW.md was restored from the original input ZIP with an external backup; scoring labels were never changed.
''',encoding='utf-8')
    # This dependency file must be in the bundle as well as beside it.
    requirements=(OUT/'extra-requirements.txt').read_bytes()
    name=(OUT/'extra-requirements.txt').relative_to(ROOT).as_posix()
    blobs[name]=requirements;manifest['files'][name]=hashlib.sha256(requirements).hexdigest()
    blobs['bundle-manifest.json']=(json.dumps(manifest,indent=2)+'\n').encode()
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as z:
        for n,b in sorted(blobs.items()):z.writestr(n,b)
    inputs=Path(tempfile.mkdtemp(prefix='translated-fresh-bundle-'))
    with zipfile.ZipFile(target) as z:assert z.testzip() is None;z.extractall(inputs)
    run=subprocess.run([sys.executable,str(inputs/'scripts/retrieval/evaluate_translated_fresh_reranker.py'),'--preflight'],cwd=inputs,capture_output=True,text=True)
    (OUT/'extracted-bundle-preflight.txt').write_text(run.stdout+run.stderr)
    assert run.returncode==0,run.stderr
    info={'status':'prepared_not_run','zip_bytes':target.stat().st_size,'zip_sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'notebook_syntax':'passed','zip_crc':'passed','extracted_bundle_preflight':'passed','translation_successes':24,'translation_failures':0,'gpu_inference_run':False,'weights_downloaded_locally':False}
    (OUT/'preparation.json').write_text(json.dumps(info,indent=2)+'\n');print(json.dumps(info,indent=2))

if __name__=='__main__':main()