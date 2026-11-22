# SQL Agent v3.1 cohort freeze v1

**Status: FROZEN for the authorized 40-case SQL Agent benchmark, using scorer/protocol v3.3.0.** The original `README.md`, draft freeze manifest, case set, Gold SQL, and Gold results remain unchanged as historical evidence.

## Review reconciliation

The two recorded decision files each contain 40 `APPROVE` decisions for the same pinned cases and Gold inputs. The versioned adjudication lists every case and records zero disagreements:

- [`ADJUDICATION_V3_1_CONSENSUS_20261122.json`](ADJUDICATION_V3_1_CONSENSUS_20261122.json)
- [`FREEZE_MANIFEST_V3_1_FROZEN_V1.json`](FREEZE_MANIFEST_V3_1_FROZEN_V1.json)

Reviewer 1's approval was logged from the user's confirmation after the HTML page failed to retain a durable export. Reviewer 2 is a separate friend according to the user; the reviewer's identity and direct export are unavailable. The browser page restores both recorded approvals, but the original per-case actions, timestamps, rationales, signatures, and cryptographic identity proof are unavailable. The freeze records this provenance limitation rather than claiming independent authentication.

## Frozen inputs

- 40 cases: 30 `execute`, 5 `clarify`, 5 `abstain_without_query`.
- 30 Gold SQL definitions and 404 provisional Gold result rows.
- Case-set SHA-256: `36dbd0876167fccb954923dd4ad2f9961a31e6fd05e8d76ec5f99fecf4a012ce`.
- Gold SQL definition SHA-256: `cf8072cbce69eff02f1305e0ece9a41c1dcfaa73b8ac0b8e96c8f225bb96e0a5`.
- Frozen database fingerprint: `dbc14b99acc2920ffaeb4190ba45708982c971f0671b0b9e8114b595f2594028`.
- Fresh live preflight: [`database_preflight_v3_1_live_20261122T005320Z.json`](database_preflight_v3_1_live_20261122T005320Z.json), read-only role verified and fingerprint equal to Gold provenance.
- Application source revision: `37b5fed55a45fc30a5e46376e9e41d0abb6bb17f`.
- Benchmark harness Git revision and source hashes are pinned in the freeze manifest.
- Provider configuration and fallback chain are pinned in the manifest without storing credentials.

The runner checks all frozen hashes and the live database fingerprint before creating the SQL Agent. It will stop before model calls on any mismatch. For v3.1 it uses the frozen Gold rows directly and does not rerun Gold SQL during the Agent experiment. The raw experiment directory is immutable; resume is explicit and only resumes incomplete cases.

## Runner and scoring

Run a fresh experiment into a new, previously unused directory with `artifacts/sql-agent-bussiness/runner.py`, passing the frozen case, Gold result, Gold SQL, freeze manifest, application revision, and output path. Supply the acknowledged frozen analytics database settings in the process environment; do not store credentials in benchmark artifacts.

After the run, create a linked semantic decision record with `semantic_audit_v3_1.py`. If observed SQL has additional output columns, review each one separately with `output_safety_audit_v3_3.py`. Then invoke the runner with `--score-only` and the saved `data.json` directory plus both audit files. That path does not instantiate a SQL Agent, provider, or database connection and refuses to replace existing scores/reports.

The SQL semantic reviewer in this execution is an AI-assisted reviewer, separate from the SQL Agent output and not an authenticated human reviewer. Unclear SQL or output safety remains `REVIEW_REQUIRED`; no PASS is inferred from result similarity alone. The scorer remains unchanged.
