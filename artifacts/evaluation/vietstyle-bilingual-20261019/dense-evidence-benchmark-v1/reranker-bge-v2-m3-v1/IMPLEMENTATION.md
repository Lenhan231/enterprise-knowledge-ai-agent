# Local reranker experiment: what changed

## Existing code versus the new work

The Huy checkout already contained `scripts/retrieval/evaluate_rerankers.py`, an older Vinamilk evaluation script using `sentence_transformers.CrossEncoder`. This was benchmark code, not an active production reranker. No reranker references were found in the cached QuocAn commit fdfe6ca; current GitHub head could not be verified because fetch required authentication. Branch ownership is therefore not established by this experiment.

The new `scripts/retrieval/evaluate_vietstyle_reranker.py` uses the same installed CrossEncoder library approach and reuses the existing model-ID registry, frozen E5 snapshots, evidence scorer, summary aggregation and independent character coverage check. It does not repurpose the older Vinamilk labels or modify that runner.

Flow:

1. Verify corpus, cases, labels, candidate order and saved E5 vector hashes.
2. Reconstruct the same role/target-language-scoped dense ranking. Keep30 candidates and confirm the first10 exactly match the saved baseline.
3. Read each original question together with each candidate's original chunk text. No reference answers, gold spans, translations or labels enter the reranker inputs.
4. BGE-reranker-v2-m3 produces a raw relevance logit for each pair. Sort descending; score ties keep E5 order. Return10 original chunks, with original text/provenance.
5. Score dense10, reranked10 and the full30-candidate evidence availability using unchanged evidence v2. Report gains and regressions on all80 cases.

A CrossEncoder is the model architecture/library interface that reads a pair jointly; BGE-reranker-v2-m3 is the particular trained model/checkpoint. E5 is still the embedding model used to retrieve candidates. Document embeddings are not replaced or recalculated.

No total context-token budget is applied, as requested. Both compared outputs contain10 chunks, whose lengths may differ. The only length check is the reranker's per-pair encoder limit: configured1024, maximum actual507, zero truncated pairs. It is not a cap on combined LLM context.

## Model and hardware

- Model: BAAI/bge-reranker-v2-m3; checkpoint953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e.
- Official model card: https://huggingface.co/BAAI/bge-reranker-v2-m3 — multilingual sequence-classification reranker, query+passage inputs, higher relevance score ranks first.
- XLM-Roberta sequence-classification head with one output; no newly initialized replacement classification head or Qwen causal-LLM adaptation.
- GPU: RTX2060; float16; batch2; peak allocated CUDA memory about1114MiB.
- Runtime files downloaded once to the WSL Hugging Face cache. Subsequent benchmark run is offline/local; document/question text is not sent to an inference API. Model card/images are not required runtime files, and the cache loader specifies the exact runtime allowlist.
- Mean30-pair added reranking time402ms, median379ms, after warm-up. This excludes model loading, dense retrieval, preflight, evidence scoring and generation. It is not end-to-end application latency.

## Results

| Query → documents | E5 dense10 | BGE reranked10 | Evidence available in all30 |
|---|---:|---:|---:|
| VI→VI | 17/19 | 17/19 | 19/19 |
| EN→EN | 14/19 | 14/19 | 18/19 |
| VI→EN | 9/19 | 12/19 | 14/19 |
| EN→VI | 12/19 | 12/19 | 14/19 |

Nineteen eligible intents per direction; Q14 approval roles remain unresolved. The full30 availability column is diagnostic, not comparable to a10-chunk output and not an oracle top10 selection claim. The80 cases reuse20 paired intents; evidence labels are assistant-reviewed/post-hoc and alternatives remain non-exhaustive. No generated answers were evaluated.

### Vietnamese details

- Q20 fixed: the approval table Manual parser index13 moves from E5 rank12 to reranker rank7, so the full normal approval workflow enters top10.
- Q13 improves from6/9 required components to8/9: SOP parser index1 (preparation/blind count) moves to reranker rank8. The no-deletion/traceable adjustment guard SOP index4 remains at rank21, so the complete intent still fails.
- Q15 regresses from4/4 to2/4: the Adjustment Transaction ID form is reranker rank11 and the no-deletion guard rank27. They are present in the30-candidate pool but omitted from top10.
- Therefore the overall VI→VI complete-intent count stays17/19, although required component coverage changes57/61→58/61. This does not justify enabling reranking globally.

Other directions: EN→EN gainsQ15 but losesQ01; VI→EN gainsQ07/Q15/Q16/Q17 but losesQ01; EN→VI gainsQ17 but losesQ01. For Q01 EN→EN, the explicit not-approved training cover is reranked13th, leaving approval status unsupported by the accepted spans in final10. As with all label-based failures, equivalent unlabelled evidence would require separate review, not automatic score rewriting.

## Checks

Four new unit tests cover ACL/language filtering and dense ties; finite/count/shape/unique-score validation and tie handling; full question+passage preflight rejecting truncation; and a rank12 evidence-promotion example with original chunk text/provenance preserved.

All80 cases and2,400 saved relevance scores were replayed without loading the model. Verification reconstructs dense candidates, independently sorts saved logits using NumPy stable sorting, and recomputes all three evidence views; source-character set coverage cross-checks the scorer's interval unions. Baseline matches the existing v2 scores. Old source/vector/label/results hashes remain unchanged.

## Reproduce

From the repository in WSL, with model runtime files already cached:

```bash
.venv/bin/python -m unittest discover -s tests -p test_vietstyle_reranker.py -v
# Verification only: no encoder or GPU required.
.venv/bin/python scripts/retrieval/evaluate_vietstyle_reranker.py --verify-only
# New GPU run: fresh folder preserves this completed result.
.venv/bin/python scripts/retrieval/evaluate_vietstyle_reranker.py --output-dir artifacts/evaluation/vietstyle-reranker-repeat
```

For closer timing reproduction, set OMP_NUM_THREADS=4 and MKL_NUM_THREADS=4 once in the shell. This run also used HF_HUB_OFFLINE=1 and TOKENIZERS_PARALLELISM=false. Defaults already select CUDA, batch2 and the pinned model revision.

On another machine, download only the needed runtime files first:

```bash
.venv/bin/hf download BAAI/bge-reranker-v2-m3 --revision 953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e --include config.json model.safetensors tokenizer.json tokenizer_config.json special_tokens_map.json sentencepiece.bpe.model
```

All data artifacts must be present at their frozen relative paths. Do not index evidence/question/reference-answer files. A partial/failed run must not be treated as completed; config.json records status and completed-case count.

## Remaining work

This step implements and tests the local benchmark, not production integration. Given the Vietnamese regression, inspect evidence selection for Q15 and the short guard sentence shared with Q13 before making reranking a default. The dense30 pool already contains all required annotated VI evidence; improving selection/context is a more direct next investigation than re-embedding the database. Any next tuning needs fresh/held-out evaluation to avoid optimizing repeatedly against these20 known intents.

No production retrieval, embedding_service.py, document chunks/vector database, translation or LLM code changed. Work is uncommitted; handoff updated.

## Follow-up correction: Q15

Read Q15_ANALYSIS.md. The canonical transaction-ID table fell to rank11, but the same field is explicitly present in the prose/form extraction at rank4. Thus one of the reported component losses is a missing alternative label, not an actual missing fact in final context. The explicit no-delete/direct-source-edit instruction remains omitted (rank27); related no-overwrite history text at rank9 is only partial. Original scores remain unchanged.
