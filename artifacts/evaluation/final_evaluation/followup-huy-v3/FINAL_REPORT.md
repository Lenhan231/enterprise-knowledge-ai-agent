# Dashboard and Report follow-up with Huy’s Knowledge v3 evidence

Production application revision `a2f57e67e45b965cda4e901d3e2647861655e4c5`. The evaluation used frozen inputs and unchanged production code.

## Chapter IV · Methodology

The Dashboard cohort used 20 cases, four per objective. The Report cohort used 40 cases across Sales Performance and Inventory Risk. It included 10 numerical, eight citation, six template, six missing-data, six RBAC, and four delivery cases. Valid controls included expected abstention and partial delivery. Invalid cases changed one input or contract element at a time. The replay measured downstream validation, rendering, and delivery using scripted inputs at the SQL, retrieval, and draft boundaries.

Dashboard and Report numerical evidence continued to use Nhân’s independently verified frozen SQL pilot to preserve the fixture basis across rounds. The labeled synthetic controls also carried forward. Inventory Risk citation cases replayed Huy’s human-reviewed grade-2 excerpts for T021 and T039. The published answer scores below are upstream context. The reviewed excerpts supply the grounding oracle.

Dashboard replay exercised the production document builder, reconciliation, chart building, and HTML rendering. Report replay used the public template generation entry point, strict Sales JSON validator, Inventory Risk renderer, and HTTP response handler. The RBAC tests used local identities and instrumented source boundaries. The semantic pass used the existing authenticated Modal GPT-OSS-120B deployment, vLLM on one A100 80 GB GPU, with temperature 0.01, default reasoning, up to six transient retries, and a 4,000-token cap. Judgments used the frozen 0–2 per-dimension rubric and schema-checked evidence IDs. Objective failures retain their deterministic result.

## Published Knowledge evidence

Huy’s `Huy-eval-v3` commit `f290f553af13f976cfd60862e013604892aabe71`. The test-set hash matches the human-reviewed lock and the published score file matches its run manifest.

| Knowledge run | Cases | Published accuracy | Wrong seal rate | Wrongly withheld rate |
|---|---:|---:|---:|---:|
| test-prod-mminilm | 60 | 86.7% | 0.0% | 9.4% |
| test-prod | 60 | 91.7% | 0.0% | 3.8% |

T021 uses VN chunks 482 and 431. T039 uses VN chunks 629 and 398. These cases anchor positive, contradictory, unknown-citation, and uncited Report fixtures. Huy’s scorer marked both answers correct in both published runs. T039 was sealed in `test-prod-mminilm` and unverified in `test-prod`. The downstream oracle is the reviewed passage in each case. Knowledge generation and scoring were not rerun.

The follow-up reused 11 archived Modal judgments with matching input, settings, rubric, and client hashes. The semantic timing table includes retained observations. Dashboard D14 now includes the observed table values in its judge input, and Report policy cases include emitted database citation IDs and their fact-ID mappings.

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
| Report | Citation support | 6/6 | 1.5 | 4/6 (66.7%) | 1 | 1 |
| Report | Factual consistency | 7/7 | 1.571 | 5/7 (71.4%) | 1 | 1 |
| Report | Report completeness | 8/8 | 1.875 | 7/8 (87.5%) | 1 | 0 |

| Agent | Downstream cases | p50 / p95 ms | Scored Modal cases | Modal p50 / p95 ms | Reported tokens |
|---|---:|---:|---:|---:|---:|
| Dashboard | 20 | 12.75 / 21.34 | 6 | 87161.6 / 160296.13 | 6,724 over 6 calls |
| Report | 40 | 90.5 / 195.17 | 17 | 35283.73 / 62923.88 | 30,284 over 17 calls |

The synthetic Modal smoke request took **157,448 ms** and its outcome was **pass**. Modal request timings include network, possible cold start, and retries. Modal scales to zero after 60 seconds of inactivity. Downstream latency excludes Modal and upstream service work.

### Failure analysis

- **D04** A replayed revenue row of 13,299,822.25 passed through as a KPI. The independently verified oracle was 13,299,821.25. [Raw observation](results/dashboard/D04.raw.json)
- **D12** The Dashboard forwarded the November 13, 2026 scope and still accepted a source payload whose bound date was October 31, 2026. [Raw observation](results/dashboard/D12.raw.json)
- **D16** The table displayed 13,299,821.25 while a KPI from a second result for the same scope displayed 13,299,999.25. Both tiles completed. [Raw observation](results/dashboard/D16.raw.json)
- **R15** The report completed with a claim that goods held for quality inspection count as sellable. Huy’s reviewed T021 passage VN#482 explicitly excludes them. Modal citation support was 0/2. [Raw observation](results/report/R15.raw.json)
- **R16** The report completed with a claim that a low-stock signal automatically creates a purchase order. Huy’s reviewed T039 passage VN#398 limits the signal to replenishment review. Modal citation support was 1/2. [Raw observation](results/report/R16.raw.json)

**Judge input limitation in D14.** The structured judge input included the table’s revenue values but omitted its rendered month column. Modal deducted credit for the missing month. The delivered HTML contains January and February 2025 alongside the two revenue values. [Rendered dashboard](results/dashboard/D14.html)

**Rubric inconsistency in R16.** Modal’s rationale identified the direct contradiction in S2, but its 1/2 score also credited the supported SQL table. The rubric reserves 1/2 for partial support without a direct contradiction. The reported Modal score is the raw judgment, and the deterministic case remains a failure. [Judgment records](judge/judgments.json)

The focused production suite passed 67 tests and skipped 8 opt-in PostgreSQL cases. [Production test log](results/production_tests.log)

## Chapter VI · Conclusions and limitations

The Dashboard successfully preserved and rendered the frozen data in the valid controls. Deliberate discrepancies in the replayed source boundary exposed three places where a successful source status took precedence over the independent oracle. These tests show the downstream trust boundary. They do not measure how often the live SQL Agent emits those discrepancies.

The Report rejected changed quantitative claims, malformed templates, and out-of-scope evidence requests in the isolated cases. The citation checks verified reference IDs, but two contradictory qualitative claims passed production validation. Their contradictions are directly visible in the frozen policy excerpts. Modal scores provide a separate review of the outputs.

The cohorts are small, purposively selected, and reuse upstream evidence across controls and mutations. Some fixtures use synthetic inputs. Sales Performance and Inventory Risk expose different output contracts. DOCX was parsed structurally. The evaluation does not measure live retrieval, database permission enforcement, unrestricted generation, or Word visual layout. Report and Dashboard correctness rates are conditional on replay. Dashboard judge inputs included the expected handling of controlled requests, so chart suitability used an unblinded, rubric-guided review. Automated judge agreement is not independent verification.

Reproduction steps are in the [README](../README.md). The [November 21 baseline](../FINAL_REPORT.md) used an earlier application revision and earlier policy fixtures. The differences cannot be attributed solely to the Knowledge evidence update.
