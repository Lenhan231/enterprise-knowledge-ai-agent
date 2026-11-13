# Investigation: gold chunks lost by automatic language-aware hybrid

## Finding

The six observed gold-chunk losses are reproducible consequences of the current rank-fusion policy. They are not caused by translation failing or by corpus drift: using the saved generated queries against the hash-matched read-only snapshot reproduced all 48 BM25 top-10 rankings and all 48 hybrid top-10 rankings exactly. No new translation or answer-generation calls were made.

The gold chunks remain in the lexical candidate list. Four losses receive zero dense contribution because their full dense ranks exceed the top-100 candidate cutoff. The other two are present in dense candidates but rank weakly and are pushed below the top-10 output cutoff. All six losses concern Long Hau.

## Exact lost cases

Ranks are 1-based. Dense rank is measured over all 249 scoped chunks; only its first 100 contribute to hybrid. BM25 rank below is the merged language-aware lexical rank, not raw within-language rank.

| Original query | Case | Gold chunk | Local VI BM25 rank | Merged BM25 rank | Full dense rank | Final hybrid rank |
|---|---|---:|---:|---:|---:|---:|
| en | Q14 | 7 | 1 | 2 | 225 | 25 |
| vn | Q14 | 7 | 1 | 2 | 234 | 25 |
| en | Q15 | 9 | 5 | 10 | 145 | 39 |
| vn | Q15 | 9 | 5 | 10 | 209 | 37 |
| vn | Q18 | 20 | 2 | 4 | 95 | 14 |
| vn | Q19 | 21 | 3 | 6 | 64 | 11 |

## Why fusion does this

The final score is:

```text
score = 1 / (60 + dense_rank) + 2 / (60 + merged_BM25_rank)
```

Each term contributes only when the chunk is within that method’s top 100. This rewards agreement between methods. It does not guarantee preservation of a strong single-method hit. With k=60, differences between nearby lexical ranks are small enough for even moderate dense support to reverse the order.

For English Q14, the correct audit-firm chunk is first in Vietnamese BM25 and second after language-list fusion. Its dense rank is 225, so its score is only `2/(60+2) = 0.03225806`. The final tenth-place chunk scores `0.04124116`; the gold chunk falls to rank 25. The first hybrid result is an English PVFCCo audit-opinion passage: it scores well for generic audit terms but belongs to the wrong company for this question.

For Vietnamese Q19, the gold profit table is merged-BM25 rank 6 and dense rank 64: `2/66 + 1/124 = 0.03836755`. The tenth-place chunk scores `0.03839775`, a margin of only about `0.00003021`. The gold table finishes rank 11. This is an output-cutoff effect, not missing source data.

## Underlying data and query issues

1. **OCR and chunk context are plausible contributors to weak dense ranks.** Q15’s signing-date gold chunk is heavily corrupted signature-block text. It still contains “Ngày 17 tháng 3 năm 2009”, but has little clear audit-report context. Dense ranks it 145 for English and 209 for Vietnamese. Q18/Q19 are structured table fragments with OCR labels and numeric values. These observations explain what to investigate; they do not experimentally prove how much OCR repair would improve embeddings.
2. **Entity-specific questions still search both companies.** Some high-ranked candidates concern PVFCCo while the question explicitly names Long Hau. Company metadata on the reports was previously verified as the shared `Commerce Demo` value, so the present benchmark cannot rely on that field to separate the real entities. Production entity/document scoping should use verified metadata and explicit query/user intent, never gold labels.
3. **The first fusion step also dilutes single-language ranks.** Because the English and Vietnamese document scopes are disjoint, equal language-list RRF largely interleaves the two reports regardless of raw BM25 confidence. Long Hau’s local ranks 1/2/3/5 become merged ranks 2/4/6/10 in these cases. This is deliberate coverage of both language groups, but it can reward the other report even on an entity-specific question.
4. **Translation is not the immediate cause of these six additional losses.** BM25 and hybrid used exactly the same saved translations. BM25 found every lost gold chunk. Translation quality can still affect the experiment globally, but cannot explain why an already-found chunk disappears only after dense fusion.

## Exact-chunk misses are not always answer misses

- **Q19:** hybrid rank 2 returns Long Hau chunk 51. It explicitly contains profit-before-tax values `172.820.359` and `61.592.023`, with `Ngàn VNĐ` and current/prior-year columns—the same requested figures as gold chunk 21. The exact gold label is missed, but another retrieved passage appears sufficient to answer the question. A reviewer should add it as an alternative valid judgment after confirming source context.
- **Q14:** hybrid retrieves Long Hau’s cover chunk 0, which includes an OCR rendering of Ernst & Young. That may support the auditor identity even though labeled chunk 7 is missing. Human review is needed; do not count all six exact-label losses as six proven answer failures.
- **Q15:** the labeled signing block with the requested date drops to rank 39/37. This deserves priority review for actual evidence loss.
- **Q18:** the labeled revenue table drops from BM25 rank 4 to hybrid rank 14; the top result is a tax-adjustment passage. Review whether any returned passage contains both net-revenue figures before declaring answer failure.

## Hybrid also has a measured benefit

English Q08 gains its gold production/import-plan chunk: merged BM25 rank 15, dense rank 1, hybrid rank 6. Fusion can rescue a dense-only hit, so deleting dense universally is not justified by the six losses. Across English cases the two losses and one gain explain the net recall difference.

## Recommended next actions

1. **Audit labels first:** have a reviewer check Q14/Q19 alternate evidence and add valid alternatives as a separately versioned judgment set. Keep the original labels/results frozen. Otherwise tuning may optimize for an arbitrary exact chunk rather than answer evidence.
2. **Keep automatic language-aware BM25 as the current comparison baseline.** Its recall is 77.08% English / 83.33% Vietnamese versus hybrid 72.92% / 66.67%. Do not change application defaults from this small scoped set.
3. **Run one focused fusion experiment:** test a lexical-first policy that protects a small lexical head while allowing dense to fill the remaining positions, or test reduced dense influence. Evaluate retrieval recall and alternative-evidence coverage on held-out cases. These are proposed experiments, not verified fixes; Q08 must remain a regression check.
4. **Fix source context:** preserve source company, section/table title, years, units and page when embedding table/signature chunks. Validate OCR repair against the original PDF rather than inventing text. Re-embedding changes the corpus and requires versioned labels and a new benchmark snapshot.
5. **For application integration:** correct real company/document-language metadata, allow explicit document/company scope, and test a mixed corpus with permission-denial cases. A new reranker is an option only if the simpler fusion adjustment remains insufficient.

## Code locations

- `scripts/retrieval/evaluate_bilingual_two_document_benchmark.py`: `fuse()`; per-language BM25 scope; `hybrid = fuse([dense, lexical[:100]], [1.0, 2.0])`.
- `src/core/retrieval/methods/dense.py`: dense candidate ordering and output limit.
- `src/core/retrieval/methods/bm25.py`: corpus-local BM25 ranking.
- No production ranking code was changed by this investigation.

## Evidence and reproduction

- [Trace JSON](automatic-fusion-loss-investigation-20261016.json): component ranks, score contributions, top-10 competitors and source excerpts for changed cases.
- [Original automatic run](scoped-automatic-translation.json).
- Reproduce: `.venv/bin/python scripts/retrieval/trace_automatic_fusion_losses.py` (requires GPU embedding environment and read-only database access; uses saved translations, no translation API calls).
- Corpus SHA-256: `2d894fb2a63095586eb0f7abba9781a3a9ba1273446a38943363777622a6f83e`.
- Limitations: two-report exact-chunk benchmark, 24 paired intents, sparse judgments, no generated-answer evaluation. Alternative-evidence observations above are a targeted text inspection, not an independently scored answer-quality benchmark.
