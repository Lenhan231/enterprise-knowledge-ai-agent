# Frozen fresh v1: translated hybrid vs dense candidates

Completed on Colab NVIDIA L4/FP32; returned and locally verified 2026-10-21. Download copied into colab-results/ with source byte checks; original retained. Matching input ZIP used for independent artifact replay. User-approved questions/evidence, corpus and E5 vectors are unchanged.

## Complete required evidence in final10

| Query → document | Dense → plain BGE | Translated hybrid → plain BGE | Dense pool30 | Hybrid pool30 |
|---|---:|---:|---:|---:|
| vi->vi | 12/12 | 12/12 | 12/12 | 12/12 |
| en->en | 12/12 | 12/12 | 12/12 | 12/12 |
| vi->en | 12/12 | 12/12 | 12/12 | 12/12 |
| en->vi | 10/12 | 12/12 | 10/12 | 12/12 |

Total complete cases46/48 →48/48; required components107/112 →112/112. EN→VI improves10/12 →12/12 and23/28 →28/28 components. All other directions remain complete. These48 directional cases reuse12 paired bilingual intents; they are not48 independent questions.

## Paired gains and regressions

- F03 EN→VI (emergency-PO reason, service impact, approver): annotated Manual chunk5 moves from dense global rank187 (outside baseline candidate30) to hybrid candidate rank4, then BGE rank2. All3 components recovered.
- F08 EN→VI (SKU/size/color/location and no merging similar variants): annotated SOP chunk2 moves from dense global rank33 to hybrid candidate rank6, then BGE rank1. Both components recovered.
- No full-case or required-component regressions. No cases lose evidence inside the hybrid candidate30. Rerankers achieve all evidence available in their respective candidate pools on this set.
- Fresh same-run dense/plain control agrees with original plain reranker evidence for all48 cases; raw dense agrees with all48 previous cases. Both arms were rescored with the same BGE checkpoint/runtime. Shared query/anchor pairs reuse exactly matching NEW scores, not historical logits.

## Translation quality caveat

All24 API translations completed without parse/API errors, which does not guarantee correct terminology. F08 EN→VI includes “cổ phiếu” (financial shares) for inventory “stock”. Its original source query was: “May similar variants be combined during a count, and which identifiers must distinguish counted stock?” The stored automatic translation is: “Các biến thể tương tự có thể được kết hợp trong quá trình đếm, và những định danh nào phải phân biệt cổ phiếu đã được đếm?” Retrieval still recovered the right passage via other matching terms and reranking. This is a real semantic error despite a successful retrieval score. The translation is preserved; no post-result edits to questions, labels, translations or rankings were made.

## What this supports

The combined translated-hybrid candidate method fixes the two known missing-candidate cases under the frozen experimental scope. It supports continuing with translated hybrid plus plain reranking as a promising integration candidate. It does not establish100% production retrieval/answer accuracy, independently held-out generalization, or isolate translation from lexical search/fusion as the causal contributor. This follow-up targeted misses already identified in the fresh set, so it is development evaluation.

## Recipe and verification

Existing intfloat/multilingual-e5-base query/document vectors; existing QueryTranslator with Groq openai/gpt-oss-20b/auto language detection (24 question texts explicitly approved for external translation). Original query supplies dense embedding; EN/VN lexical queries are routed to verified target-language document scopes. Actual production translated_hybrid.search reused through the offline adapter: internal300/branch, RRF60, dense1/lexical2, fused30. Both arms plain BAAI/bge-reranker-v2-m3 revision953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e FP32/batch4, final10. All5 target-language documents/admin scope. No extra predecessor context or answer generation.

BM25 uses saved PostgreSQL simple lexemes, production query cleanup and formula with corpus-local eligible statistics; numeric SQL parity was checked before inference. Stable chunk-ID BM25 ties replace unavailable live database row UUIDs. Therefore this is an offline production-method adapter, not a claim of bit-identical live database ordering.

Local replay passed48 candidate pairs/96 rankings/2880 score entries, shared-input lineage and independent character coverage. Max observed BGE pair502/1024 tokens, zero truncation. Shared Colab rerank compute51.00s; excludes API translation preparation, setup/loading and evaluation, and is not independent arm latency or end-to-end answer time.

## Recommended next step

Keep these results and labels frozen. Review translation terminology and test independently authored questions (including workbook numeric/table rows and harder cross-language phrasing) before claiming general improvement. Integrate main processing separately after fixing its table-order regression, then validate exact source/provenance compatibility. Production service integration also needs its embedding/index compatibility and verified language scope checked. No such integration, new model/download, re-embedding, database mutation or deployment was performed during result analysis.
