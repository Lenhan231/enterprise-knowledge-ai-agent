# Frozen fresh-reviewed-v1

12 bilingual paired intents, 24 texts, 48 directional cases; 28 required components per direction. All 12 eligible. Assistant-prepared and reviewed, user-approved in chat on 2026-10-21; no independent held-out claim. Sources remain simulated business documents. F04 and F09 clarifications are recorded in changes.json. Categories and overlapping intents remain as disclosed in the assessment; no workbook numeric-row question was added.

Original draft, assessment, sources, vectors and production code are unchanged. evidence.json uses the existing score_evidence schema and real parser-source offsets, converted through exact source_spans mappings. No guessed offsets or synthetic parser provenance. F02/F05/F12 accept alternative source passages per component. Evidence units contain the answer detail; document/actor/row identity is fixed by its source coordinates. They measure exact annotated component retrieval, not generated-answer correctness or general relevance.

Verify from project root (no model or network required):

    .venv/bin/python scripts/retrieval/freeze_fresh_review_set.py --verify-only --self-check

The command checks frozen hashes, exact quotes, provenance, bilingual cases, positive/empty/component-omission evidence checks and tamper rejection. It does not rewrite frozen files. Build refuses to overwrite this directory. manifest.json hashes canonical LF file bytes; .gitattributes keeps frozen files LF. External JSONL files are hashed after CRLF-to-LF normalization, without changing JSON content strings. The historical laptop draft manifest used CRLF bytes; its historical hashes are preserved.

The legacy validate_vietstyle_evidence.py and experiment loader are hard-coded to Q01-Q20 and are NOT the validator/runner for this fresh set. Reuse score_evidence with sources loaded from evidence.json; the runner adapter, new query embeddings, frozen E5 candidate pools and new reranker inference remain next steps. No retrieval benchmark has run. Never reuse old-question logits for these questions.

Keep this version fixed during comparisons. Corrections require a new version and consistent rescoring of every method. Do not index questions, labels, review notes or answers. No model download, database change, generation evaluation, candidate selection or production integration occurs in this freeze.
