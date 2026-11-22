# December 2 capstone evaluation

This package replays 20 Dashboard cases and 40 Report cases against the pinned production source. It includes deterministic observations, raw HTML and report exports, and independently reported Modal semantic judgments.

## November 22 follow-up with Huy’s Knowledge v3

The [follow-up](followup-huy-v3/FINAL_REPORT.md) runs 20 Dashboard and 40 Report cases on `main` at `a2f57e67`. Reviewed Knowledge v3 excerpts supply the oracle for the updated Inventory Risk citation fixtures. The November 21 run remains available in the root of this package.

```powershell
git fetch origin main Huy-eval-v3
$pin = 'a2f57e67e45b965cda4e901d3e2647861655e4c5'
$env:EKAI_EVAL_SOURCE = Join-Path $env:TEMP 'ekai-final-a2f57e67e45b'
git worktree add --detach $env:EKAI_EVAL_SOURCE $pin
$env:EKAI_EVAL_FOLLOWUP = '1'
$env:PYTHONUTF8 = '1'
$py = (Resolve-Path '.venv/Scripts/python.exe').Path
$e = 'artifacts/evaluation/final_evaluation/scripts'
& $py -B "$e/freeze.py"
& $py -B "$e/replay.py"
& $py -B "$e/judge.py"
& $py -B "$e/verify.py" --repeat
& $py -B "$e/summarize.py"
Remove-Item Env:EKAI_EVAL_FOLLOWUP
```

Reuse the pinned worktree if it already exists. The freeze step checks the locked test-set hash and the published Knowledge score artifact against Huy’s manifests. Only Grade 2 passages in the human review of T021 and T039 supply the new policy evidence. The archived scores remain upstream context. The judge reuses archived judgments where the input and configuration match.

## Reproduce

Run from the repository root using its existing Python environment. The example is for PowerShell.

```powershell
$pin = '60eafaee964a6de48a0c8d13925e3207d5116588'
$env:EKAI_EVAL_SOURCE = Join-Path $env:TEMP 'ekai-final-60eafaee964a'
git worktree add --detach $env:EKAI_EVAL_SOURCE $pin
$py = (Resolve-Path '.venv/Scripts/python.exe').Path
$env:PYTHONUTF8 = '1'
$e = 'artifacts/evaluation/final_evaluation/scripts'
& $py -B "$e/replay.py"
& $py -B "$e/summarize.py"
& $py -B "$e/verify.py" --repeat
```

If the pinned worktree already exists, omit the worktree creation line. Replay verifies its commit, tracked-file cleanliness, upstream source hashes, and frozen dataset hashes. It uses scripted drafts and source data. It requires no database access or app generation calls. `freeze.py` regenerates the fixture files from the pinned Git objects. Use it to check fixture construction when needed.

### Modal judging

The original local client is preferred when available. A snapshot of that same client is included for reproduction. Set `MODAL_JUDGE_BASE_URL` and `MODAL_JUDGE_API_KEY` in the ignored repository-root `.env` or the process environment. Use the authorized deployed GPT-OSS-120B endpoint. A `--smoke` run sends one synthetic rubric check. The saved execution uses the supplied Modal deployment with temperature 0.01 and capped completions. The runner validates JSON shape and captures the underlying API response and usage.

```powershell
& $py -B "$e/judge.py" --smoke
& $py -B "$e/judge.py"
& $py -B "$e/summarize.py"
& $py -B "$e/verify.py" --repeat
```

Matching scored judgments are reused by input, rubric, settings, and client hash. Use `--retry-blocked` for another attempt on unscored requests. Archived judgments are sufficient to regenerate the delivered report without provider access.

### Focused production tests

```powershell
Push-Location $env:EKAI_EVAL_SOURCE
$env:PYTHONPATH = 'src'
& $py -B -m unittest tests.dashboard.test_dashboard_reconciliation tests.dashboard.test_dashboard_charts tests.dashboard.test_dashboard_structured_generation tests.report.test_report_inventory tests.report.test_sales_performance_flow tests.report.test_report_grounding tests.report.test_report_delivery tests.report.test_report_templates
Pop-Location
```

## Evidence and scoring

- `config/provenance.json` pins source and input hashes. SQL cases P01–P05 come from Nhân’s published pilot. For supported cases, the values are checked against the independent reference execution. P05 supplies its frozen unsupported behavior. The later 40-case SQL preparation is still pending review and its provisional rows are outside this evaluation. The two policy excerpts come directly from the pinned VietStyle source document. Huy’s unpublished benchmark is outside this cohort.
- `datasets/evidence.json` holds the frozen values used for replay. `SYN-TREND`, `SYN-CATEGORY`, and the Report ratio are synthetic validation controls. Sales report coverage and row-grain adaptation are scripted at the downstream boundary. The evidence supplies verified 2025 revenue, with other unavailable Sales metrics kept missing.
- `results/*/cases.json` records the expected outcome, observations, individual assertions, and optional judge input. The accompanying raw JSON records the source boundary, application output, and delivery metadata. Saved DOCX, Markdown, JSON, and HTML files are actual production-rendered bytes. HTML and DOCX here are evaluated structurally.
- `judge/judgments.json` preserves scored or blocked requests and the exact settings. The judge evaluates semantic aspects on a frozen, eligible subset. Deterministic results use the evidence and production contracts, with automated judgment recorded separately.
- `FINAL_REPORT.md` contains the aggregate tables, examples, and thesis text for Chapters IV and VI.
