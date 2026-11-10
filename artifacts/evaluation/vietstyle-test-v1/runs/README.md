# Run outputs and judge verdicts

Raw evidence for the Knowledge AI evaluation (report Sections IV.4–IV.5 and VI.1.5–VI.1.9). This folder holds the locked TEST set runs (Section VI.1.9); development-set runs are in `../../vietstyle-heldout-v1/runs/`.

## File types

| Pattern | Contents |
|---|---|
| `<arm>.json` | Runner output (`scripts/agents/run_vietstyle_arm.py`): per question, the answer, retrieved and cited passages, verifier outcome and timing |
| `<arm>.scored.json` | Scored with Judge A (gpt-oss-120b) plus deterministic metrics (`scripts/agents/score_vietstyle_arm.py score`) |
| `<arm>.scored.codex.json` | Scored with Judge B (Codex verdicts) |
| `<arm>.scored.claude.json` | Scored with Judge C (Claude verdicts; test set only) |
| `judge-verdicts-*.jsonl` | Raw external judge verdicts. In the `-nofaith` versions, faithfulness is nulled, because Judge B did not read the source pages |
| `B2-after.json`, `E2E-K-after.json` (+ `.scored.json`, `judge-verdicts-*-testv1-after*.jsonl`) | Tuned RAG and Knowledge mode after the improvements of Section VI.1.10; `B2.json` is the matching before run |
| `latency-after-fix-20261106.json` | V1–V6 latency after the corrective fixes (`scripts/operations/measure_pipeline_latency.py`) |

The judge prompts themselves are not stored. They can be regenerated exactly with `score_vietstyle_arm.py export <runs> --output <file>`, which takes the run files, the question set and the policy text.

## Arm names

| Arm | Report name |
|---|---|
| B0 | Closed-book |
| B1 | Naive RAG |
| B2 | Tuned RAG |
| B4 | Tuned RAG without verifier |
| E2E-K | Knowledge mode (API) |
| E2E | Auto mode (API) |
| B2-fix, E2E-fix, E2E-K-fix | Same arms after the corrective fixes (commit f88613d) |
| B2-clean | Tuned RAG, unrelated uploads deactivated |
| B2-clean-vn | Tuned RAG, unrelated uploads deactivated and Vietnamese policy active (final configuration) |

## Run conditions

Each run file records its configuration and a free-text note in `configuration`, and the SHA-256 of the question set in `dataset_sha256`.

Some rows were re-run after provider rate limits; the runner keeps only the final row per question. Rows that failed because of the provider are listed by `failed_row()` in the runner.
