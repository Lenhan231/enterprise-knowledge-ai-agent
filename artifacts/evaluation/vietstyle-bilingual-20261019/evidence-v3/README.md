# Evidence v3: Q15 duplicate-source fix

This is a targeted annotation correction, not a retrieval/model change. Only Q15.transaction_id gains one Vietnamese source alternative. The original separately extracted table remains valid; the same explicit post-approval transaction-ID field in the SOP prose is now valid too. It is parser index5, Unicode[888,947), quote “Adjustment Transaction ID Mã giao dịch điều chỉnh sau duyệt”. English was reviewed and already accepts its corresponding form/prose occurrence, so it is unchanged.

Everything else remains unchanged: source files and hashes, questions/reference answers, all old evidence spans, all other requirements, the mandatory Q15.history control, and unresolved Q14. v2 remains preserved. There are66 components (61 required ready,2 unresolved,3 optional),199 spans (100VI/99EN),19 fully-ready intents. See annotation-changes.json for exact before/after, source hash and semantic rationale.

## Result

E5+BGE reranker Q15 VI→VI changes from2/4 to3/4 components. The transaction ID was already in its fourth result; the corrected label now recognizes it. Q15 still fails complete-evidence scoring because the explicit no-deletion/direct-source-edit sentence is missing from its final10. Reranker total VI→VI remains17/19. No model behavior improved through this correction.

The same v3 labels were applied to all three dense candidates and the saved BGE reranker:320 case rankings replayed with independent character-coverage checks. BGE-M3 dense now recognizes its Q15 evidence and moves14→15 complete VI→VI cases; E5 remains17 and Qwen14. See ../dense-evidence-benchmark-v1/rescored-evidence-v3/comparison.md for all directions. No encoder, GPU, translation or generation rerun; no total context-token budget.

## Code changes

rescore_vietstyle_evidence.py now accepts --previous-evidence and --previous-results-dir to compare consecutive label revisions while preserving the original embedding artifacts. Optional --reranker-report rescores a verified existing reranker report by replaying saved logits. It does not reload the model or alter ranking. Default label/version behavior remains compatible with the original v1→v2 experiment.

Two new tests in tests/test_evidence_v3.py verify that only this component/one span changes, English was already covered, the complete field description is still necessary, and missing history is not forgiven. The validator's --self-check also rejects damaged quotes and wrong-language source references. No production/database/embedding changes.

## Reproduce

```bash
.venv/bin/python scripts/retrieval/validate_vietstyle_evidence.py --folder artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v3 --self-check
.venv/bin/python -m unittest discover -s tests -p 'test_evidence*.py' -v
```

To repeat the rescore, use a fresh output directory (existing completed outputs are protected):

```bash
.venv/bin/python scripts/retrieval/rescore_vietstyle_evidence.py \
  --evidence artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v3/evidence.json \
  --previous-evidence artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v2/evidence.json \
  --previous-results-dir artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/rescored-evidence-v2 \
  --reranker-report artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/reranker-bge-v2-m3-v1/results.json \
  --output-dir artifacts/evaluation/vietstyle-evidence-v3-repeat
```

Historical embedding/reranker runners remain pinned to their recorded evidence v2 baseline for reproducibility; use this explicit rescore path to evaluate those saved rankings under v3. A future inference experiment should explicitly pin the chosen label version. Do not index labels/questions/reference answers or use them to pick chunks. This is post-hoc assistant-reviewed annotation, not independently certified/held-out performance.
