# Final evaluation for the December 2, 2026 capstone defense

Production application revision `60eafaee964a6de48a0c8d13925e3207d5116588`. The evaluation used frozen inputs and unchanged production code.

## Chapter IV · Methodology

The Dashboard cohort used 20 cases, four per objective. The Report cohort used 40 cases across Sales Performance and Inventory Risk. It included 10 numerical, eight citation, six template, six missing-data, six RBAC, and four delivery cases. Valid controls included expected abstention and partial delivery. Invalid cases changed one input or contract element at a time. The replay measured downstream validation, rendering, and delivery using scripted inputs at the SQL, retrieval, and draft boundaries.

Nhân’s five-case SQL pilot was the business evidence source. Supported gold rows, SQL, and parameters were checked against its independently executed frozen reference. Nhân’s later 40-case SQL preparation remained pending human review at the pinned revision. The provisional rows were excluded. Two Dashboard evidence sets and the Report percentage fixture used labeled synthetic inputs. Report document checks used two excerpts from the repository’s VietStyle operating policy. Huy’s unpublished benchmark was excluded at the user’s direction. No upstream SQL or Knowledge benchmark was rerun.

Dashboard replay exercised the production document builder, reconciliation, chart building, and HTML rendering. Report replay used the public template generation entry point, strict Sales JSON validator, Inventory Risk renderer, and HTTP response handler. The RBAC tests used local identities and instrumented source boundaries. The semantic pass used the existing authenticated Modal GPT-OSS-120B deployment, vLLM on one A100 80 GB GPU, with temperature 0.01, default reasoning, up to six transient retries, and a 4,000-token cap. Judgments used the frozen 0–2 per-dimension rubric and schema-checked evidence IDs. Objective failures retain their deterministic result.

## Chapter IV · Results

| Metric | Dashboard | Report |
|---|---:|---:|
| Deterministic case accuracy | 17/20 (85.0%) | 38/40 (95.0%) |
| Invalid detection | 5/8 (62.5%) | 18/20 (90.0%) |
| False rejection | 0/12 (0.0%) | 0/20 (0.0%) |
| Numerical assertion exact-match | 28/30 (93.3%) | 4/4 (100.0%) |
| Valid template compliance | 0/0 (N/A) | 3/3 (100.0%) |
| Deterministic cases blocked | 0 | 0 |
| Modal coverage | 6/6 (100.0%) | 17/17 (100.0%) |

Accuracy counts cases satisfying every applicable objective check and the expected acceptance outcome. Invalid detection counts invalid controls that production rejected, clarified, or withheld. False rejection counts valid controls that production failed to accept as intended. Numerical exact-match counts individual applicable row, chart-series, KPI, and typed-fact assertions. Valid template compliance counts valid template controls. Blocked cases are listed separately.

| Agent | Primary case category | Deterministic pass |
|---|---|---:|
| Dashboard | Fidelity | 3/4 (75.0%) |
| Dashboard | Chart | 4/4 (100.0%) |
| Dashboard | Filters | 3/4 (75.0%) |
| Dashboard | KPI | 3/4 (75.0%) |
| Dashboard | Failure | 4/4 (100.0%) |
| Report | Numerical | 10/10 (100.0%) |
| Report | Citation | 6/8 (75.0%) |
| Report | Template | 6/6 (100.0%) |
| Report | Missing | 6/6 (100.0%) |
| Report | RBAC | 6/6 (100.0%) |
| Report | Delivery | 4/4 (100.0%) |

### Automated semantic scores

| Agent | Dimension | Scored / eligible | Mean / 2 | Full credit | Score 1 | Score 0 |
|---|---|---:|---:|---:|---:|---:|
| Dashboard | Chart suitability | 6/6 | 1.833 | 5/6 (83.3%) | 1 | 0 |
| Report | Citation support | 6/6 | 1.167 | 3/6 (50.0%) | 1 | 2 |
| Report | Factual consistency | 7/7 | 1.571 | 5/7 (71.4%) | 1 | 1 |
| Report | Report completeness | 8/8 | 1.875 | 7/8 (87.5%) | 1 | 0 |

| Agent | Downstream cases | p50 / p95 ms | Scored Modal cases | Modal p50 / p95 ms | Reported tokens |
|---|---:|---:|---:|---:|---:|
| Dashboard | 20 | 11.85 / 23.63 | 6 | 35372.63 / 179303.4 | 6,830 over 6 calls |
| Report | 40 | 96.15 / 186.27 | 17 | 40077.08 / 64104.23 | 27,829 over 17 calls |

The synthetic Modal smoke request took **157,448 ms** and its outcome was **pass**. Modal request timings include network, possible cold start, and retries. Modal scales to zero after 60 seconds of inactivity. Downstream latency excludes Modal and upstream service work.

### Failure analysis

- **D04** A replayed revenue row of 13,299,822.25 passed through as a KPI. The independently verified oracle was 13,299,821.25. [Raw observation](results/dashboard/D04.raw.json)
- **D12** The Dashboard forwarded the November 13, 2026 scope and still accepted a source payload whose bound date was October 31, 2026. [Raw observation](results/dashboard/D12.raw.json)
- **D16** The table displayed 13,299,821.25 while a KPI from a second result for the same scope displayed 13,299,999.25. Both tiles completed. [Raw observation](results/dashboard/D16.raw.json)
- **R15** The writer said a missing product should count as zero inventory. The cited policy explicitly says it must not. The report completed. Modal citation support was 0/2. [Raw observation](results/report/R15.raw.json)
- **R16** The writer said stock quantities should be summed across dates. The cited policy explicitly forbids that operation. The report completed. Modal citation support was 0/2. [Raw observation](results/report/R16.raw.json)

**Judge input limitation in D14.** Modal reported that the table lacked revenue. Its input contained tile metadata and chart series. The independent HTML check found table values of 10 and 20 and verified that they agreed with the KPI of 30. The deterministic pass stands. [Rendered dashboard](results/dashboard/D14.html)

**Evidence alias limitation in R11.** Modal found the policy claim supported by S2. It deducted credit because the report’s SQL and fact identifiers were absent from the judge evidence map, which supplied the same data through P04. The citation score includes that input limitation. [Raw observation](results/report/R11.raw.json)

The focused production suite passed 66 tests and skipped 8 opt-in PostgreSQL cases. [Production test log](results/production_tests.log)

## Chapter VI · Conclusions and limitations

The Dashboard successfully preserved and rendered the frozen data in the valid controls. Deliberate discrepancies in the replayed source boundary exposed three places where a successful source status took precedence over the independent oracle. These tests show the downstream trust boundary. They do not measure how often the live SQL Agent emits those discrepancies.

The Report rejected changed quantitative claims, malformed templates, and out-of-scope evidence requests in the isolated cases. The citation checks verified reference IDs, but two contradictory qualitative claims passed production validation. Their contradictions are directly visible in the frozen policy excerpts. Modal scores provide a separate review of the outputs.

The cohorts are small, purposively selected, and reuse upstream evidence across controls and mutations. Some fixtures use synthetic inputs. Sales Performance and Inventory Risk expose different output contracts. DOCX was parsed structurally. The evaluation does not measure live retrieval, database permission enforcement, unrestricted generation, or Word visual layout. Report and Dashboard correctness rates are conditional on replay. Dashboard judge inputs included the expected handling of controlled requests, so chart suitability used an unblinded, rubric-guided review. Automated judge agreement is not independent verification.

Reproduction steps are in the [README](README.md). Per-case records, raw artifacts and judge responses are retained under [results](results/) and [judge](judge/).
