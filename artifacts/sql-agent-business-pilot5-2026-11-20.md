# SQL Agent business-quality pilot — 5 cases

**Run date:** 2026-11-20
**Code under test:** `origin/main` at `c0e5aa7753ffffde20390fb19a91b168c4a0ab9b`
**Path:** SQL Analytics Agent + Cloudflare `@cf/openai/gpt-oss-20b` + Jev `typesafe/jev-1.14`
**Scope:** SQL Agent only; Knowledge and Auto were not included. Read-only analytics identity; no writes.

## What this benchmark answers

The main metric is **end-to-end exact result accuracy**: among questions that the available data can answer, how many returned the exact ordered rows and values in an independently prepared gold result? A query passing SQL validation or executing successfully does not count as a correct answer by itself.

This scores the complete SQL Agent path (intent interpretation, schema selection, SQL generation, validation and execution). It does not isolate or rank the LLM on its own.

## Results

| Metric | Result | What it measures |
|---|---:|---|
| **End-to-end exact result accuracy** | **1/4 (25%)** | Answerable questions whose complete result rows match gold |
| SQL semantic contract | 3/4 (75%) | Required tables, metric, dates, filters, grouping, ordering, tie-break and limit retained in SQL |
| Approved execution acceptance | 3/4 (75%) | Answerable questions that reached the approved SQL execution path |
| Exact rows among executed questions | 1/3 (33%) | Strict row and output-column equality for executed queries |
| Requested values among executed questions | 2/3 (67%) | Requested fields match, allowing an extra returned field |
| Silent business-scope loss | 1/4 (25%) | A required filter was dropped although SQL executed |
| Validation failure | 1/4 (25%) | Answerable query was blocked by SQL validation |
| False refusal | 0/4 (0%) | Answerable query refused or clarified instead of being handled |
| Safe abstention on unsupported request | 1/1 (100%) | Unsupported request stopped without executing business SQL |
| Explanation of unsupported dimensions | 1/2 (50%) | Clarification explicitly covered each missing requested dimension |
| Jev availability | 0/4 | All four attempts returned HTTP 402; recall@5 is not measurable |
| Latency, descriptive only | p50 8.19 s; p95 14.85 s | End-to-end latency across only five selected traces |

Small denominators mean these are pilot counts, not stable population estimates.

## Frozen questions and observed outcomes

There were four answerable cases and one deliberately unsupported case. Prompts, requested semantics and data-based golds were frozen before model calls. The repository identifies the Commerce source as synthetic competition data, not real retailer results (`src/core/database/document_repository.py:416,468,472`). This report includes the five selected gold/actual result sets, not a full database export.

| Case | Exact frozen request | Route and outcome |
|---|---|---|
| P01 | `What was total revenue for 2025?` | Annual revenue fixed compiler; exact query and result |
| P02 | `Khách hàng nào có nhiều đơn hàng đã giao nhất trong năm 2025? Trả về top 5 customer_id và số đơn hàng; nếu bằng nhau sắp customer_id tăng dần.` | Intent + schema selection + SQL generation; executed without `order_status = 'delivered'`, so result is wrong |
| P03 | `Top 5 products by units sold from delivered orders between 2025-04-01 and 2025-06-30; return product_id and units, ties by product_id ascending.` | Intent + schema selection + SQL generation; generated SQL kept quantity/date/status semantics, but ranking validation read “return” as product returns and rejected it |
| P04 | `Tại snapshot 2026-11-13, cho tôi 5 sản phẩm có tồn kho cao nhất, gồm product_id, product_name và stock_on_hand; nếu bằng nhau sắp product_id tăng dần.` | Inventory mapping + typed compiler; requested values match, but output adds `snapshot_date`, failing strict full-row equality |
| P05 | `Tại snapshot 2026-11-13, tồn kho từng kho và lead time của nhà cung cấp cho từng sản phẩm là bao nhiêu?` | Unsupported-schema handling; safely clarified without business SQL, but clarification omitted the missing warehouse dimension |

## Gold data vs SQL Agent output

These are the selected cases' gold rows and observed Agent rows, not a dump of the Commerce tables. Currency metadata is absent, so P01 is reported without assuming a currency.

**P01 — 2025 revenue**

| Gold | SQL Agent |
|---:|---:|
| 13,299,821.25 | 13,299,821.25 |

**P02 — delivered orders per customer, 2025**

| Rank | Gold customer_id | Gold orders | Agent customer_id | Agent orders |
|---:|---:|---:|---:|---:|
| 1 | 1924 | 4 | 58578 | 5 |
| 2 | 41034 | 4 | 102 | 4 |
| 3 | 42962 | 4 | 1924 | 4 |
| 4 | 102 | 3 | 41034 | 4 |
| 5 | 6121 | 3 | 42962 | 4 |

Agent SQL counted all statuses; the gold filters `order_status = 'delivered'`.

**P03 — units sold by product, delivered orders in Q2 2025**

| Rank | Gold product_id | Gold units | SQL Agent output |
|---:|---:|---:|---|
| 1 | 690 | 11 | No rows; validator rejected the generated SQL |
| 2 | 761 | 11 | No rows; validator rejected the generated SQL |
| 3 | 782 | 11 | No rows; validator rejected the generated SQL |
| 4 | 808 | 11 | No rows; validator rejected the generated SQL |
| 5 | 1059 | 11 | No rows; validator rejected the generated SQL |

**P04 — stock at snapshot 2026-11-13**

| Rank | Gold product_id | Gold product_name | Gold stock | Agent product_id | Agent product_name | Agent stock |
|---:|---:|---|---:|---:|---|---:|
| 1 | 1974 | UrbanVN RP-49 | 60 | 1974 | UrbanVN RP-49 | 60 |
| 2 | 2091 | UrbanVN UC-26 | 60 | 2091 | UrbanVN UC-26 | 60 |
| 3 | 556 | SaigonFlex UC-21 | 59 | 556 | SaigonFlex UC-21 | 59 |
| 4 | 2180 | PhoenixWear UC-10 | 59 | 2180 | PhoenixWear UC-10 | 59 |
| 5 | 2219 | VietMotion RP-16 | 59 | 2219 | VietMotion RP-16 | 59 |

All requested values match. SQL Agent also returned `snapshot_date = 2026-11-13` on each row, which causes the strict full-row mismatch.

**P05 — unsupported warehouse and supplier lead-time data**

| Gold rows | Agent rows | Status |
|---|---|---|
| None; schema lacks warehouse and supplier lead-time fields | None | Clarification required; zero business queries executed |

## Runtime and safety evidence

- Selected cohort: 5 traces, 8 Cloudflare calls (2 intent, 1 metric mapping, 4 SQL generation, 1 repair), and 4 Jev attempts.
- Across the run and recovery attempts: 8 SQL Agent invocations for 5 unique questions. Three additional invocations corrected/recovered telemetry; they are not extra benchmark cases.
- Three approved business queries executed; zero restricted unverified executions.
- Jev returned HTTP 402 on every attempt, so the agent used its full-schema fallback. The final prompt schema covered 4/4 gold-required table pairs; that is fallback coverage, not a Jev success score.
- The read-only source-data fingerprint was unchanged before and after the corrective runs.

## Measurement deviation

The first tracer did not preserve a provider method signature, invalidating the P02/P03 intent traces; those traces are excluded. The initial runner also failed to persist P05 after the agent returned because its oracle JSON lacked a P05 entry. P05's no-query expectation was already frozen in the case file, and the oracle record was completed from that contract before the recovered P05 trace was scored. P01/P04 use the original unaffected traces; P02/P03 use corrected traces; P05 uses the recovered trace. The first P05 attempt's provider/query event counts cannot be reconstructed. The raw discrepancy is stated here rather than counted as clean telemetry.

## What to benchmark next

Expand to 40 frozen, reviewed questions: 8 direct/deterministic, 8 filtered aggregations, 8 ranking/tie/limit, 6 date/follow-up, 6 inventory snapshot/mapping, and 4 unsupported/security-scope cases. Prepare gold SQL/results before model calls and score each case individually.

To compare SQL LLMs, hold the case set, database snapshot, prompt, schema selector, validator and execution path fixed; change only the SQL LLM. Evaluate Jev separately once the 402 blocker is resolved, comparing top-5 required-table recall against a full-schema baseline. Keep Auto and Knowledge outside the SQL Agent score.

## Audit identifiers

- Python runtime: `3.11.16`
- Frozen cases SHA-256: `540490ad342951a74c37d2777508dbfac9ed9cec6ec5d89086a4f6145c9e218d`
- Gold oracle SHA-256: `38f184a5d368c34df19d5c54108e4b389f5ad0f7bdad4c82b1194b10bdb8c6ba`
- Offline scorer SHA-256: `c432a8fe1d6860c8f3709b10cca187571086bbfcf627424a0502b4124198af46` (local audit copy; not part of the pushed artifact)
- Detailed traces and raw outputs are retained locally outside the repository; the pushed artifact contains aggregate findings and no result rows.
- Offline rescoring of the selected traces: **PASS**; artifact checksums: **PASS**.
- Unit/integration/dashboard/report/Auto suites: **NOT RUN** (this was a live quality pilot; no production code was changed).
