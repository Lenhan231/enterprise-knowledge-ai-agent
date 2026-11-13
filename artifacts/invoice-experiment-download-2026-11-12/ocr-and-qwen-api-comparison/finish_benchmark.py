from __future__ import annotations
import json, os, subprocess, sys, time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
ART=ROOT/'artifacts/invoice-pilot-50-new-vietocr'
ENV_PATH=ROOT.parent/'.env'
KERNEL='ltrngnhn/invoice-50-qwen3-1-7b-benchmark'

def load_env():
    env={**os.environ}
    for raw in ENV_PATH.read_text().splitlines():
        line=raw.strip()
        if not line or line.startswith('#') or '=' not in line: continue
        k,v=line.split('=',1)
        env.setdefault(k.strip(),v.strip().strip('"').strip("'"))
    return env

def kaggle(args,env,timeout=90):
    return subprocess.run(['/tmp/kaggle-venv/bin/kaggle',*args],env=env,text=True,capture_output=True,timeout=timeout)

env=load_env()
while True:
    p=kaggle(['kernels','status',KERNEL],env)
    status=(p.stdout or p.stderr).strip()
    print(time.strftime('%Y-%m-%d %H:%M:%S'),status,flush=True)
    upper=status.upper()
    if 'KERNELWORKERSTATUS.COMPLETE' in upper: break
    if 'KERNELWORKERSTATUS.ERROR' in upper or 'KERNELWORKERSTATUS.CANCEL' in upper:
        log=kaggle(['kernels','logs',KERNEL],env)
        (ART/'qwen17b_kernel_error.log').write_text(log.stdout+'\n'+log.stderr)
        print('Qwen 1.7B Kaggle kernel failed; saved logs.',flush=True)
        raise SystemExit(2)
    time.sleep(120)

out=ART/'qwen17b-kaggle-output'; out.mkdir(parents=True,exist_ok=True)
p=kaggle(['kernels','output',KERNEL,'-p',str(out),'--file-pattern','qwen17b_results\\.json'],env,timeout=900)
print('Output download exit:',p.returncode,flush=True)
if p.returncode:
    print(p.stdout[-3000:],p.stderr[-3000:],flush=True); raise SystemExit(p.returncode)
files=list(out.rglob('qwen17b_results.json'))
if len(files)!=1: raise RuntimeError(f'Expected one qwen17b_results.json, found {files}')
qwen=json.loads(files[0].read_text(encoding='utf-8'))
rows=qwen.get('results',{})
if len(rows)!=50: raise RuntimeError(f'Expected 50 Qwen 1.7B results, got {len(rows)}')

sys.path.insert(0,str(ROOT/'src'))
sys.path.insert(0,str(ART))
from run_model_benchmark import score
while True:
    pth=ART/'model_results.json'
    if pth.exists():
        current=json.loads(pth.read_text(encoding='utf-8'))
        counts={name:len(rows) for name,rows in current.get('providers',{}).items()}
        print('Provider result counts:',counts,flush=True)
        if all(counts.get(name,0)>=50 for name in ('modal','gemini')): break
    time.sleep(60)

# Re-read just before atomic write so current API results are preserved.
pth=ART/'model_results.json'; current=json.loads(pth.read_text(encoding='utf-8'))
current.setdefault('providers',{})['qwen17b']=rows
scored,summary=score(list(rows.values()))
current.setdefault('scores',{})['qwen17b']=scored
current.setdefault('metrics',{})['qwen17b']=summary
current.setdefault('metadata',{})['qwen17b_model']=qwen.get('metadata',{}).get('model_id','Qwen/Qwen3-1.7B')
current['metadata']['qwen17b_revision']=qwen.get('metadata',{}).get('revision')
current['metadata']['qwen17b_source_commit']=qwen.get('metadata',{}).get('source_commit')
tmp=pth.with_suffix('.tmp');tmp.write_text(json.dumps(current,ensure_ascii=False,indent=2),encoding='utf-8');tmp.replace(pth)

lines=['# Invoice 50 new VietOCR benchmark','',f"Shared OCR: {qwen.get('metadata',{}).get('ocr_repo')} @ {qwen.get('metadata',{}).get('ocr_revision')}",f"Qwen3-1.7B revision: {qwen.get('metadata',{}).get('revision')}",'','| Model | Success | Whole invoice exact | Item row exact | Description CER | Description WER | Mean end-to-end s |','|---|---:|---:|---:|---:|---:|---:|']
for name in ('modal','qwen17b','gemini'):
    m=current.get('metrics',{}).get(name,{})
    lat=m.get('end_to_end_latency_seconds',{}).get('mean')
    lines.append(f"| {name} | {m.get('success_count',0)}/{m.get('sample_count',0)} | {m.get('whole_invoice_exact_rate',0):.1%} | {m.get('item_row_exact_accuracy',0):.1%} | {m.get('description_cer',0) or 0:.3f} | {m.get('description_wer',0) or 0:.3f} | {lat if lat is not None else '—'} |")
(ART/'benchmark_summary.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print('Benchmark merged and summarized:',ART/'benchmark_summary.md',flush=True)
