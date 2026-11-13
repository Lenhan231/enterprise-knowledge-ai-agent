"""Build portable frozen inputs and a Colab notebook; never package credentials/weights."""
import argparse
import io
import json
from pathlib import Path
import subprocess
import sys
import zipfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
parser = argparse.ArgumentParser(description=__doc__)
group = parser.add_mutually_exclusive_group()
group.add_argument("--parent-context", action="store_true", help="Create separate actual-neighbor experiment artifacts")
group.add_argument("--parent-plain", action="store_true", help="Compare original plain passages with predecessor text only")
args = parser.parse_args()
parent_run = args.parent_context or args.parent_plain
if parent_run:
    HERE = ROOT / ("artifacts/evaluation/colab-reranker-parent-plain-20261020" if args.parent_plain else "artifacts/evaluation/colab-reranker-parent-20261020")
    HERE.mkdir(parents=True, exist_ok=True)
commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
folders = ["artifacts/evaluation/vietstyle-bilingual-20261019", "artifacts/evaluation/embedding-comparison-20261018"]
raw = subprocess.check_output(["git", "-c", "core.autocrlf=false", "archive", "--format=zip", commit, *folders], cwd=ROOT)
scripts = ["evaluate_reranker_source_context", "evaluate_vietstyle_reranker", "evaluate_embedding_candidates",
           "evaluate_embeddings", "evaluate_rerankers", "compare_vietstyle_evidence",
           "rescore_vietstyle_evidence", "validate_vietstyle_evidence"]
code = [ROOT / f"scripts/retrieval/{name}.py" for name in scripts]
code += [ROOT / f"src/core/evaluation/{name}.py" for name in ("evidence_metrics", "retrieval_metrics")]
with zipfile.ZipFile(io.BytesIO(raw)) as inputs, zipfile.ZipFile(HERE / "reranker_colab_inputs.zip", "w", zipfile.ZIP_DEFLATED) as out:
    for item in inputs.infolist():
        if not item.is_dir():
            out.writestr(item.filename, inputs.read(item))
    for path in code:
        out.writestr(path.relative_to(ROOT).as_posix(), path.read_bytes().replace(b"\r\n", b"\n"))
    out.writestr("SNAPSHOT_COMMIT.txt", commit + "\n")


def cell(kind, source):
    value = {"cell_type": kind, "metadata": {}, "source": source.splitlines(keepends=True)}
    if kind == "code":
        value.update(execution_count=None, outputs=[])
    return value


cells = [
    cell("markdown", """# Free Colab: BGE reranker source-context experiment

Choose **Runtime → Change runtime type → T4 GPU** (or another available free GPU).
Do not buy compute units. If no free GPU is available, try later or use your home PC.
Run the cells in order. The ~2.3 GB model downloads **inside Colab**, never onto your laptop.
No Hugging Face token or repository access is needed: upload `reranker_colab_inputs.zip`.
Both arms use the same pinned BGE model/runtime, E5 top30 candidates, 80 cases,
and evidence v3. No total context-token cap; original passages alone earn coverage.
This is a post-hoc diagnostic on 20 paired intents, not held-out answer accuracy.
"""),
    cell("code", """%pip -q install sentence-transformers==6.0.1 transformers==5.17.0 huggingface-hub==1.31.0 numpy==2.4.6 python-dotenv
# If Colab asks to restart the session, restart and continue from the next cell.
"""),
    cell("code", """import os
os.environ.update(OMP_NUM_THREADS='4', MKL_NUM_THREADS='4', TOKENIZERS_PARALLELISM='false', HF_HUB_DISABLE_XET='1')
import torch
assert torch.cuda.is_available(), 'No GPU assigned. Select a free GPU runtime; this notebook will not silently run on CPU.'
print('PyTorch:', torch.__version__, 'GPU:', torch.cuda.get_device_name(0))
"""),
    cell("code", """from google.colab import files
from pathlib import Path
import zipfile

uploaded = files.upload()  # Select reranker_colab_inputs.zip from your laptop.
assert 'reranker_colab_inputs.zip' in uploaded, 'Upload the input bundle, not the notebook.'
work = Path('/content/reranker_experiment')
work.mkdir(exist_ok=True)
with zipfile.ZipFile('reranker_colab_inputs.zip') as bundle:
    assert all((work / name).resolve().is_relative_to(work.resolve()) for name in bundle.namelist())
    bundle.extractall(work)
del uploaded
os.chdir(work)
print('Inputs extracted. No credentials were included.')
"""),
    cell("code", """import subprocess, sys
output = Path('/content/reranker_results')
base = [sys.executable, '-X', 'utf8', 'scripts/retrieval/evaluate_reranker_source_context.py',
        '--input-root', str(work), '--output-dir', str(output)]

# First downloads the pinned model to Colab, then checks input lengths and runs both arms.
# A completed output folder is protected. To repeat, choose a NEW output folder.
subprocess.run(base + ['--device', 'cuda', '--allow-download'], check=True)
"""),
    cell("code", """# Verify all saved rankings and evidence scores without loading the model again.
subprocess.run(base + ['--verify-only'], check=True)

import json
r = json.loads((output / 'results.json').read_text())
print('Direction | Plain complete intents | Source-context complete intents')
for direction in ('vi->vi', 'en->en', 'vi->en', 'en->vi'):
    a, b = [r['summary'][arm][direction] for arm in ('plain', 'source_context')]
    print(direction, f\"{a['full_evidence_cases_at_10']}/{a['full_intent_eligible_cases']}\",
          f\"{b['full_evidence_cases_at_10']}/{b['full_intent_eligible_cases']}\")
"""),
    cell("code", """# Download result artifacts only: no model weights, token, or source-data cache.
import shutil
assert output.exists(), 'Run the experiment cell first.'
archive = shutil.make_archive('/content/reranker_context_results', 'zip', root_dir=output)
files.download(archive)
# Return this ZIP to the project/Codex for Q13/Q15 and regression analysis.
# If inference failed, you can still use this cell to save partial checkpoints;
# config.json will identify incomplete runs. They are NOT completed results.
"""),
]
if parent_run:
    for value in cells:
        text = "".join(value["source"])
        text = text.replace("reranker_colab_inputs.zip", "reranker_parent_colab_inputs.zip")
        text = text.replace("reranker_experiment", "reranker_parent_experiment")
        text = text.replace("reranker_results", "reranker_parent_results")
        text = text.replace("reranker_context_results", "reranker_parent_context_results")
        text = text.replace("Source-context complete intents", "Parent-context complete intents")
        text = text.replace("Plain complete intents", "Metadata-only complete intents")
        text = text.replace("'--input-root', str(work), '--output-dir', str(output)]",
                            "'--input-root', str(work), '--output-dir', str(output), '--context-mode', 'parent']")
        value["source"] = text.splitlines(keepends=True)
    cells[0]["source"] = ("# Free Colab: preceding-source-context experiment\n\n"
        "Select a free GPU runtime and run cells in order. Upload `reranker_parent_colab_inputs.zip`.\n"
        "The model downloads inside Colab, never to your laptop. No credentials are needed.\n"
        "Treatment: source/section headers plus one immediately preceding passage for short candidates\n"
        "when document/language/location/access roles match and section titles do not conflict.\n"
        "Control is metadata-only; treatment adds preceding source text. This isolates one added factor.\n"
        "JSON uses legacy 'plain' keys for the control; config.control_mode explicitly records 'metadata'.\n"
        "Same pinned model, E5 top30, 80 cases and evidence v3; both arms run on this GPU.\n"
        "Only original selected candidate text earns evidence coverage; neighboring text is ranking-only.\n"
        "There is no total context-token cap. Inputs exceeding the per-pair model limit fail preflight.\n"
        "This post-hoc diagnostic is not held-out evaluation.\n").splitlines(keepends=True)
if args.parent_plain:
    for value in cells:
        text = "".join(value["source"])
        text = text.replace("reranker_parent_colab_inputs", "reranker_parent_plain_colab_inputs")
        text = text.replace("reranker_parent_experiment", "reranker_parent_plain_experiment")
        text = text.replace("reranker_parent_results", "reranker_parent_plain_results")
        text = text.replace("reranker_parent_context_results", "reranker_parent_plain_results")
        text = text.replace("Metadata-only complete intents", "Plain complete intents")
        text = text.replace("'--context-mode', 'parent'", "'--context-mode', 'parent-plain'")
        value["source"] = text.splitlines(keepends=True)
    cells[0]["source"] = ("# Plain reranking vs preceding text (no added metadata prefixes)\n\n"
        "Select a free GPU runtime, upload `reranker_parent_plain_colab_inputs.zip`, and run cells in order.\n"
        "Model files download on Colab, not on your laptop. No token or paid API is needed.\n"
        "Control: original plain passages. Treatment: same eligible predecessor text as experiment 2,\n"
        "without added filename/section/table metadata prefixes. Native headings in original source text remain.\n"
        "Fixed E5 top30, model revision, evidence v3, 80 cases and top10; both arms use this GPU runtime.\n"
        "Neighbor text is ranking-only. Evidence scoring credits only the original selected anchors.\n"
        "No total context-token cap; per-pair inputs above 1024 tokens fail rather than truncate.\n"
        "This is a post-hoc diagnostic, not held-out answer quality.\n").splitlines(keepends=True)
bundle_name = "reranker_parent_plain_colab_inputs.zip" if args.parent_plain else "reranker_parent_colab_inputs.zip" if parent_run else "reranker_colab_inputs.zip"
notebook_name = "reranker_parent_plain_colab.ipynb" if args.parent_plain else "reranker_parent_context_colab.ipynb" if parent_run else "reranker_context_colab.ipynb"
notebook = {"cells": cells, "metadata": {"colab": {"name": notebook_name},
             "accelerator": "GPU", "kernelspec": {"name": "python3", "display_name": "Python 3"}},
            "nbformat": 4, "nbformat_minor": 5}
(HERE / "reranker_context_colab.ipynb").write_text(json.dumps(notebook, indent=2) + "\n", encoding="utf-8")
if parent_run:
    (HERE / "reranker_colab_inputs.zip").replace(HERE / bundle_name)
    (HERE / "reranker_context_colab.ipynb").replace(HERE / notebook_name)
print("Bundle MB:", round((HERE / bundle_name).stat().st_size / 1024**2, 1))
print("Notebook:", HERE / notebook_name)

# Validate the portable input path without loading/downloading a model.
extracted = ROOT / ".venv/colab-bundle-verification"
extracted.mkdir(exist_ok=True)
with zipfile.ZipFile(HERE / bundle_name) as bundle:
    assert bundle.testzip() is None
    assert not any(Path(name).name in {".env", "model.safetensors"} for name in bundle.namelist())
    bundle.extractall(extracted)
subprocess.run([sys.executable, "-X", "utf8", "-c",
    "from pathlib import Path; import sys; sys.path.insert(0, 'scripts/retrieval'); "
    "import evaluate_reranker_source_context as e; d=e.prepare(Path.cwd()); "
    "print('Portable inputs verified:', len(d['rows']), 'passages,', len(d['cases']), 'cases; labels', d['provenance']['labels_sha256'])"],
    cwd=extracted, check=True)
for value in cells:
    if value["cell_type"] == "code":
        source = "".join(value["source"])
        compile("\n".join(line for line in source.splitlines() if not line.startswith("%")), "colab_cell", "exec")
