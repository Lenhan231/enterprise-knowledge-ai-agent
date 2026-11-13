# Translated hybrid / plain reranker comparison

Status: Colab reranking completed and locally verified on 2026-10-21. See RESULTS.md and findings.json; original outputs are in colab-results/. Preparation protocol below is preserved. Evidence remains fresh-reviewed-v1 with the original manifest hash c8f9dae06fd70e9e897912aa4a0a7488e98993c88af2b182a1406db72c51f6f3. All24 Groq translations succeeded with auto language detection. No gold bilingual counterparts were supplied as translations. Approved by user in chat before external API calls. API records/usage are in translations.json; source documents, labels and credentials were not translation inputs.

The existing production translated_hybrid.search handles rank fusion and language routing, through a frozen-corpus repository. E5 original query/document vectors are unchanged. Each arm reranks30 and returns10 with the same plain BGE model. Production hybrid internally takes top_k*10=300 per dense/lexical branch before fusion; this is distinct from the30 candidates delivered to reranking. RRF60, dense1/BM252, equal EN/VN lexical fusion. Five verified target-language documents compete in each case; admin scope, no gold-source filter. The out-of-target-language BM25 scope is empty, as required by the fixed directional experiment.

PostgreSQL simple lexemes were extracted in a read-only transaction over supplied frozen strings, without reading/writing document tables. Python scoring uses production BM25 constants, corpus-local statistics and query cleanup; two SQL numeric parity checks passed. Offline BM25 uses stable chunk-ID ties rather than unavailable original live database row UUIDs. This is a documented offline adapter difference, not a claim of bit-identical live SQL ordering. Fiscal-year prioritization is irrelevant for these frozen queries (none requests an explicit fiscal year).

Run via the supplied notebook, or in the Colab remote VS Code terminal:

    cd /content
    unzip -q translated_fresh_colab_inputs.zip -d translated_fresh_experiment
    cd translated_fresh_experiment
    python -m pip install -r artifacts/evaluation/colab-translated-hybrid-fresh-v1/extra-requirements.txt
    OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 TOKENIZERS_PARALLELISM=false HF_HUB_DISABLE_XET=1 python -u scripts/retrieval/evaluate_translated_fresh_reranker.py --output-dir /content/translated_fresh_results --allow-download

Base sentence-transformers/transformers dependencies are the same versions as the previous Colab run; notebook includes full install. extra-requirements.txt adds only OpenAI SDK/Pydantic for importing the existing production contracts; no API key or external translation request occurs on Colab. Reuse the existing GPU runtime/cache if still available. Both control and treatment reranker logits are computed NEW on this same runtime, with shared-input reuse. Old control results are only checked diagnostically; no cross-run score mixing. Record GPU/software and shared compute timings; those are not independent per-arm/end-to-end latency.

Verify:

    python scripts/retrieval/evaluate_translated_fresh_reranker.py --output-dir /content/translated_fresh_results --verify-only

Download that results folder/ZIP and return for paired gains/losses, pool availability, F03/F08 and all regressions review. Verification must use the EXACT matching extracted input bundle. Inputs are frozen before BGE scores; do not edit labels, translations or candidate rules after seeing results. This is a follow-up on development data, not independent held-out validation or answer accuracy. Production, database records, model vectors, questions and evidence are unchanged. The accidental word run in frozen REVIEW.md was restored from the original input ZIP with an external backup; scoring labels were never changed.
