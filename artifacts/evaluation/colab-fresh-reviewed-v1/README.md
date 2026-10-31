# Fresh-reviewed-v1 Colab comparison

Status: Colab run completed and locally verified on 2026-10-21. Read RESULTS.md and findings.json; original artifacts are under colab-results/. Frozen questions/labels are unchanged. The preparation/run protocol below is preserved.

1. Open https://colab.research.google.com/ and upload fresh_reviewed_colab.ipynb.
2. Runtime > Change runtime type > GPU. Run cells in order.
3. At the file picker, upload fresh_reviewed_colab_inputs.zip from this folder.
4. The notebook downloads pinned E5 and BGE models on Colab, embeds the NEW queries, reuses saved document vectors, freezes dense30 pools and computes plain/parent-plain/narrative-parent rankings.
5. Run verification and download fresh_reviewed_results.zip. Return it here for review.

No API key, GitHub push, database access or local model download is required. Prior-question logits cannot evaluate new queries and are not used. The returned ZIP contains query vectors, candidate pools, original/context renderings, new scores, per-case rankings/evidence, software/model versions, checksums and verification. Partial results are explicitly failed and are not a completed benchmark. Output paths refuse overwrite; choose a new Colab output directory to rerun.

Protocol: identical frozen 1,063 passage corpus, existing pinned multilingual-e5-base vectors, 24 unique query texts / 48 cases across four directions, five competing target-language documents, admin scope, normalized FP32 E5 query embeddings with query: prefix/cap512, dense top30 then final10 with pinned BGE reranker FP32/cap1024. Plain and changed predecessor inputs are scored in the same run; narrative-only selection reuses exactly matching new-run scores (plain for structured tables, predecessor for narrative). This avoids duplicate inference without mixing historical runs. No new context rule or label changes. Report dense baseline, candidate30 evidence availability, all three reranker variants, required components, full success, categories and paired gains/losses. Timing records shared computation, NOT independently measured per-variant/end-to-end latency. No total context-token budget, translation/hybrid or generation. This is a small user-approved assistant-authored extension, not independent held-out proof or answer accuracy.

Local checks: frozen label/provenance validation, source/vector SHA and row alignment, offline synthetic score replay/tamper rejection, notebook Python syntax and ZIP CRC; extracted-bundle preflight must pass before use. Model/token length checks also run before Colab inference; cached-only local preflight may be recorded separately. Never index benchmark labels/questions/answers.

After return, extract safely into a new results directory, then run against the MATCHING input bundle:

    .venv/bin/python <extracted-bundle>/scripts/retrieval/evaluate_fresh_reviewed_reranker.py --output-dir <returned-results> --verify-only

The bundled code locates its own frozen inputs. Compare file hashes before trusting output; do not assume a later Git HEAD matches the inference source.
