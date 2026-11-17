# VietStyle Knowledge evaluation v3: dev and test sets

From 17 Nov 2026, these two sets replace every earlier VietStyle Knowledge set: test-v1/v2, heldout-v1, heldout-review2-v1, fresh-reviewed-v1 and baseline-30. The earlier sets and the report built on them stay unchanged as an archive.

| Set | File | Use |
|---|---|---|
| dev-v3 | `dev-v3.json` | Choose settings, tune, debug. Open freely. |
| test-v3 | `test-v3.json` | Report only. Locked by hash in `MANIFEST.json` after human review, before any run. Each configuration runs on it once, and nothing is tuned on its results. |

## Scope
Knowledge mode only: policy and document questions answered from the indexed corpus, with no SQL and no routing. The corpus is the production index exported on 17 Nov 2026: 2,121 chunks in 10 documents. The main sources are the VietStyle Enterprise Operating Policy in Vietnamese (747 chunks) and English (797 chunks), plus the inventory policy pack.

## Categories
Each set has 60 questions, 5 per category.

| id | Category | What it tests |
|---|---|---|
| `lookup` | Direct lookup | One rule, stated in one passage |
| `amount` | Amount threshold | A money amount compared with a threshold, written in different styles: `3.000.000 VND`, `3 triệu`, `3tr`, `3 củ`, `4tr5`, `500k`, `1,5 tỷ`, and boundary values |
| `calculation` | Calculation from the question | The answer needs arithmetic on numbers the user gives (for example, 3 purchases × 2,000,000 against the approval tiers) |
| `multi_part` | Multi-part question | Two or more sub-questions in one message |
| `multi_passage` | Facts across passages | The answer combines passages from different sections |
| `table` | Table content | The answer is in a table row or cell |
| `not_covered` | Not in the documents | A plausible workplace question that the corpus does not answer; expected outcome `not_covered` |
| `false_premise` | False premise or cannot conclude | The question assumes something the documents contradict, or asks for a conclusion the documents cannot support |
| `language` | English and mixed language | English questions, and Vietnamese–English mixed questions |
| `noisy` | Noisy input | No diacritics, typos, chat slang ("ê ku m xem coi…") |
| `rbac` | Role-based access | The same information asked by an allowed role and by a role without access |
| `follow_up` | Follow-up | The question needs the previous turn (`history`) |

## Item fields
```json
{
  "id": "D001",
  "category": "amount",
  "question": "…",
  "role": "employee",
  "language": "vi | en | mixed",
  "history": [{"question": "…", "answer": "…"}],
  "expected_outcome": "answer | not_covered | clarify",
  "gold": [{"document": "VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf", "chunk_index": 274, "grade": 2}],
  "must_include": ["Trưởng bộ phận"],
  "must_not_include": ["Quản lý trực tiếp"],
  "reference_answer": "…",
  "facts": ["F3.tier2"],
  "topic": "Ma trận phê duyệt và ngưỡng tiền"
}
```
- **`gold.grade`:** 2 means the passage answers the question; 1 means it supports the answer (a related rule or the same rule in the other language). nDCG uses these grades. Recall@K, Precision@K and MRR count any gold passage.
- **Translation pairs:** when a rule exists in both VN and EN, the copy in the question's language has grade 2 and the other copy has grade 1.
- **Not-covered items:** `not_covered` items have no gold passages; for these items, retrieval metrics are reported separately.
- **Required text:** `must_include` lists short exact strings, or alternatives separated by `|`, that a correct answer must contain. `must_not_include` catches the most likely wrong answer.
- **Matching rule:** matching ignores case and runs after Unicode NFC normalization. A number (for example `7`, `12`, `400.000`) only matches as a whole number, never inside a longer one, so `7` does not match `17`.
- **Natural phrasing:** questions keep how employees actually ask, with dates given without a year and no public-holiday caveats. The reference answer assumes the current year and an ordinary working week.

## Splitting dev and test (no leakage)
1. **Split by topic.** Each main policy topic (for example "Điều kiện và quyền nghỉ phép", leave eligibility and entitlement) belongs to one set, in both languages at once. `split.json` lists the assignment.
2. **Money facts are split by fact.** The approval tiers and quote tiers appear in three topics (sourcing 260–272, approval matrix 273–286, Appendix B 729–736). They are split by tier instead of by topic:
   - dev: F3 tiers 1–2 and F2 tiers 1–2 (up to 50,000,000 VND);
   - test: F3 tiers 3–4, F2 tier 3 and all of F1, the expense limits (topic 178–191).
3. **The inventory policy pack** (`01_`–`05_`) is split by document, and the Planner (`04_`) by sheet.
4. **`validate.py` enforces:**
   - no gold passage appears in both sets;
   - no fact id appears in both sets;
   - near-duplicate questions are flagged (character 3-gram Jaccard ≥ 0.5);
   - every category has exactly 5 items.

## Facts used for money
- **F1, expenses** (VN 179):
  - local meals 300,000 VND per person per meal;
  - overnight lodging 1,800,000 VND per room per night (domestic), 2,500,000 VND in designated major cities.
- **F2, quotes** (VN 261, 730):
  - tier 1: up to 5,000,000, 1 documented quote;
  - tier 2: 5,000,001–50,000,000, at least 2 comparable quotes;
  - tier 3: above 50,000,000, at least 3 written quotes or a documented sole-source justification.
- **F3, approvers** (VN 274, 730):
  - tier 1: up to 5,000,000, direct manager;
  - tier 2: 5,000,001–50,000,000, department head;
  - tier 3: 50,000,001–200,000,000, department head + Procurement + Finance;
  - tier 4: above 200,000,000, Operations Executive Board + Finance.
  - Approval goes by total commitment, not per line or first invoice.

## Known corpus fact that affects RBAC items
The VN and EN Operating Policy are `allowed_roles = {employee}`. Admin sees everything, and every other role (finance_analyst, procurement, operations, executive, …) cannot retrieve the policy. RBAC items test this behaviour as it is configured. The report flags it as a probable misconfiguration.

## Metrics
- **Retrieval:** Recall@K, Precision@K, MRR and nDCG@K, for K = 1, 5, 10.
- **Generation:** Faithfulness, Answer Relevancy and Context Precision (RAGAS); must_include accuracy; outcome accuracy (answer, not_covered or clarify).
- **Hallucination rate:** answers with at least one unsupported claim. Also reported: wrong-seal rate (unsupported but sealed), wrongly-withheld rate, and the flip rate over 3 repeats.
- **System:** p50 and p95 response time, retrieval latency, throughput at 1/2/4/8 concurrent users, and GPU utilization (local runs).
