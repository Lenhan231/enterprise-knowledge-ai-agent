#!/usr/bin/env python3
"""Create a minimal credential-free Colab bundle for frozen fresh-reviewed-v1."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'artifacts/evaluation/colab-fresh-reviewed-v1'
FROZEN=ROOT/'artifacts/evaluation/fresh-reviewed-v1'
SNAP='artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1'
MODULES=['evaluate_reranker_source_context','evaluate_vietstyle_reranker','evaluate_embedding_candidates',
         'evaluate_embeddings','evaluate_rerankers','compare_vietstyle_evidence','rescore_vietstyle_evidence',
         'validate_vietstyle_evidence','freeze_fresh_review_set','evaluate_fresh_reviewed_reranker']

def cell(kind,text):
    value={'cell_type':kind,'metadata':{},'source':text.splitlines(keepends=True)}
    if kind=='code':value.update(execution_count=None,outputs=[])
    return value

def main():
    if OUT.exists():raise ValueError('Colab package exists; preserve it and choose a new version for changes')
    manifest=json.loads((FROZEN/'manifest.json').read_text())
    names=set(manifest['inputs'])
    names.update(p.relative_to(ROOT).as_posix() for p in FROZEN.iterdir() if p.is_file())
    names.update('scripts/retrieval/'+m+'.py' for m in MODULES)
    names.update(['src/core/evaluation/evidence_metrics.py','src/core/evaluation/retrieval_metrics.py',
                  'artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v3/evidence.json',
                  SNAP+'/candidates/multilingual-e5-base/results.json',SNAP+'/candidates/multilingual-e5-base/vectors.npy'])
    blobs={name:(ROOT/name).read_bytes().replace(b'\r\n',b'\n') if not name.endswith('.npy') else (ROOT/name).read_bytes() for name in names}
    for name,data in blobs.items():
        if name.endswith('.py'):ast.parse(data.decode(),filename=name)
        if name.endswith('.json'):json.loads(data)
        assert '.env' not in Path(name).parts and not name.endswith(('.safetensors','.bin'))
    info={'dataset':'fresh-reviewed-v1','status':'prepared_not_run','files':{n:hashlib.sha256(b).hexdigest() for n,b in sorted(blobs.items())},
          'scope':'Frozen source text, labels, existing document vectors and evaluation code only; no credentials, model weights or database.'}
    blobs['bundle-manifest.json']=(json.dumps(info,indent=2)+'\n').encode()
    OUT.mkdir()
    path=OUT/'fresh_reviewed_colab_inputs.zip'
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED) as z:
        for name,blob in sorted(blobs.items()):z.writestr(name,blob)
    with zipfile.ZipFile(path) as z:assert z.testzip() is None
    cells=[cell('markdown','''# Fresh reviewed retrieval benchmark v1

48 cases / 12 paired bilingual intents, not 48 independent questions. Select a GPU runtime and run cells in order.
Upload `fresh_reviewed_colab_inputs.zip` when prompted. No GitHub clone, API key or paid inference API is required.

Pinned E5 embeds the 24 NEW query texts on Colab. Existing 1,063 document vectors are reused after hash/order checks.
All five target-language documents compete with the existing admin scope. Freeze top30 before BGE reranking.
Compare dense top10 and three reranking inputs: plain, parent-plain, narrative-parent, final10.
Use FP32 on the same GPU. Identical model inputs reuse exact new-run scores; narrative-parent uses plain table
scores and predecessor narrative scores, with verified lineage. Shared-compute timings are not independent arm latency.

Labels are assistant-prepared/reviewed and user-approved, not independent held-out gold. Added preceding context is
ranking-only; evidence is scored on ORIGINAL selected anchors. No translation layer or LLM answer generation.
Models download ONLY on Colab. Per-input limits are checked; no silent truncation and no total context budget.
'''),cell('code',"%pip -q install sentence-transformers==6.0.1 transformers==5.17.0 huggingface-hub==1.31.0 numpy==2.4.6 python-dotenv\n# If asked to restart, restart and continue with the next cell.\n"),
    cell('code',"""import os
os.environ.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false', HF_HUB_DISABLE_XET='1')
import torch
assert torch.cuda.is_available(), 'Select Runtime > Change runtime type > GPU, then rerun.'
print('PyTorch:', torch.__version__, 'GPU:', torch.cuda.get_device_name(0))
"""),cell('code',"""from google.colab import files
from pathlib import Path
import zipfile
uploaded=files.upload()  # Select fresh_reviewed_colab_inputs.zip.
assert 'fresh_reviewed_colab_inputs.zip' in uploaded, 'Select the input ZIP, not the notebook.'
work=Path('/content/fresh_reviewed_experiment')
assert not work.exists(), 'Inputs already extracted; continue below or start a fresh runtime.'
work.mkdir()
with zipfile.ZipFile('fresh_reviewed_colab_inputs.zip') as bundle:
    assert all((work/name).resolve().is_relative_to(work.resolve()) for name in bundle.namelist())
    bundle.extractall(work)
del uploaded
os.chdir(work)
"""),cell('code',"""import subprocess,sys
runner=[sys.executable,'scripts/retrieval/evaluate_fresh_reviewed_reranker.py']
# No models loaded/downloaded in this cell; validates package, labels and saved vectors.
subprocess.run(runner+['--preflight'],check=True)
"""),cell('code',"""output=Path('/content/fresh_reviewed_results')
# Downloads pinned E5/BGE models to Colab, encodes new queries, freezes candidate pools and reranks.
# Completed/partial output folders are protected. A repeat needs a NEW output path.
subprocess.run(runner+['--output-dir',str(output),'--device','cuda','--allow-download'],check=True)
"""),cell('code',"""# Offline replay: checks all scores, rendered inputs, rankings and evidence character coverage.
subprocess.run(runner+['--output-dir',str(output),'--verify-only'],check=True)
import json
report=json.loads((output/'results.json').read_text())
print('Direction | Dense | Plain | Parent | Narrative | Candidate30 availability')
for direction in ('vi->vi','en->en','vi->en','en->vi'):
    counts=[]
    for arm in ('dense_top10','plain','parent-plain','narrative-parent'):
        s=report['summary'][arm][direction]
        counts.append(f"{s['full_evidence_cases_at_10']}/{s['full_intent_eligible_cases']}")
    s=report['summary']['candidate_pool30'][direction]
    counts.append(f"{s['full_evidence_cases_at_30']}/{s['full_intent_eligible_cases']}")
    print(direction,*counts,sep=' | ')
"""),cell('code',"""# Download ONLY outputs, including partial checkpoints if an earlier cell failed.
import shutil
assert output.exists(), 'Run the benchmark cell first.'
archive=shutil.make_archive('/content/fresh_reviewed_results','zip',root_dir=output)
files.download(archive)
# Return fresh_reviewed_results.zip to Codex for independent replay and gains/losses analysis.
# A failed/partial config is NOT a completed benchmark.
""")]
    for c in cells:
        if c['cell_type']=='code':
            ast.parse(''.join(l for l in c['source'] if not l.startswith('%')))
    notebook={'nbformat':4,'nbformat_minor':5,'metadata':{'colab':{'name':'fresh_reviewed_colab.ipynb'},'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'},'accelerator':'GPU'},'cells':cells}
    (OUT/'fresh_reviewed_colab.ipynb').write_text(json.dumps(notebook,indent=2)+'\n')
    preparation={'status':'prepared_not_run','zip_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'zip_bytes':path.stat().st_size,'bundle_files':len(blobs),'notebook_code_syntax':'passed','zip_crc':'passed','models_downloaded_locally':False,'inference_run':False}
    (OUT/'preparation.json').write_text(json.dumps(preparation,indent=2)+'\n')
    (OUT/'README.md').write_text('''# Fresh-reviewed-v1 Colab comparison

Status: prepared, no inference results yet. Frozen questions/labels are unchanged.

1. Open https://colab.research.google.com/ and upload fresh_reviewed_colab.ipynb.
2. Runtime > Change runtime type > GPU. Run cells in order.
3. At the file picker, upload fresh_reviewed_colab_inputs.zip from this folder.
4. The notebook downloads pinned E5 and BGE models on Colab, embeds the NEW queries, reuses saved document vectors, freezes dense30 pools and computes plain/parent-plain/narrative-parent rankings.
5. Run verification and download fresh_reviewed_results.zip. Return it here for review.

No API key, GitHub push, database access or local model download is required. Prior-question logits cannot evaluate new queries and are not used. The returned ZIP contains query vectors, candidate pools, original/context renderings, new scores, per-case rankings/evidence, software/model versions, checksums and verification. Partial results are explicitly failed and are not a completed benchmark. Output paths refuse overwrite; choose a new Colab output directory to rerun.

Protocol: identical frozen 1,063 passage corpus, existing pinned multilingual-e5-base vectors, 24 unique query texts / 48 cases across four directions, five competing target-language documents, admin scope, normalized FP32 E5 query embeddings with query: prefix/cap512, dense top30 then final10 with pinned BGE reranker FP32/cap1024. Plain and changed predecessor inputs are scored in the same run; narrative-only selection reuses exactly matching new-run scores (plain for structured tables, predecessor for narrative). This avoids duplicate inference without mixing historical runs. No new context rule or label changes. Report dense baseline, candidate30 evidence availability, all three reranker variants, required components, full success, categories and paired gains/losses. Timing records shared computation, NOT independently measured per-variant/end-to-end latency. No total context-token budget, translation/hybrid or generation. This is a small user-approved assistant-authored extension, not independent held-out proof or answer accuracy.

Local checks: frozen label/provenance validation, source/vector SHA and row alignment, offline synthetic score replay/tamper rejection, notebook Python syntax and ZIP CRC; extracted-bundle preflight must pass before use. Model/token length checks also run before Colab inference; cached-only local preflight may be recorded separately. Never index benchmark labels/questions/answers.

After return, extract safely into a new results directory, then run against the MATCHING input bundle:

    .venv/bin/python <extracted-bundle>/scripts/retrieval/evaluate_fresh_reviewed_reranker.py --output-dir <returned-results> --verify-only

The bundled code locates its own frozen inputs. Compare file hashes before trusting output; do not assume a later Git HEAD matches the inference source.
''',encoding='utf-8')
    print(json.dumps(preparation,indent=2))

if __name__=='__main__':main()