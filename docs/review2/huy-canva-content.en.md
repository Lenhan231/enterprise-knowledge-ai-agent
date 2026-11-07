# Huy's Canva content — Review 2

Prepared 23 October 2026 for the existing 23-slide Canva template (`Review 2.pdf`). This supplies Huy's retrieval contribution, not a replacement deck. Copy only the **On-slide** blocks into Canva. Notes and source paths are for the presenter/footer. Other members own parsing quality, generation results, and deployment verification.

Main result: reviewed-r1, 20 intents / 40 question texts / 80 directional cases. Use this result consistently; the earlier 48-case development result is backup only. No new inference, tuning, API calls, or database changes were performed to prepare these slides.

## Slide 10 — Tokenization, Chunking, and Provenance

### On-slide

**Keep evidence within the model's input limit**

Source passage → model tokenizer → bounded chunks → source mapping

- Tokenizer and encoder use the same model revision.
- Oversized passages are split; table headers are retained.
- Store document, page/section, chunk ID, and source spans.

**1,063 chunks · 449,203 E5 input tokens · longest input 476/512**

### Visual

Use the existing four-box layout. Place the token totals in one bottom strip. Show one actual chunk excerpt and its document/section/source-span fields; do not use an invented chunk ID. Header and overlap tokens are included in the total.

### Speaker notes

Characters are not tokens. A passage can satisfy a character limit and still exceed the encoder window. We align the tokenizer and encoder and preserve source mapping after splitting. The frozen E5 corpus has zero inputs over 512 tokens. Text splitting targets 1,100 characters; overlap depends on the splitter, so we do not claim every chunk has 120-character overlap or that these settings are optimal. Chunking/OCR quality details belong to the ingestion owner.

### Source footer

`docs/review2/retrieval-report-stats.json`; `huy-retrieval-report.vi.md`, §2.

## Slide 11 — Embedding Model and Index Design

### On-slide

**Embedding**

- `intfloat/multilingual-e5-base`
- 768 dimensions; normalized vectors; 512-token limit
- `query:` prefix for questions; `passage:` prefix for chunks

**Index and provenance**

- PostgreSQL / pgvector; cosine similarity
- Document, company, and access filters
- Parser outputs and final chunks retain source mapping
- Model revision and vector hashes recorded in the benchmark manifest

### Visual

Keep two columns. Show “question → query vector” and “chunk → passage vector” converging on the index. Keep long revision hashes in backup material.

### Speaker notes

We use pretrained models, with no fine-tuning in this experiment. E5-base was selected using an earlier domain pilot; we do not claim it is universally best. Query and index embeddings must use compatible models and dimensions. Production migrated to E5; changing only the query model would be invalid. The frozen corpus retains stale Qwen preparation metadata, but the actual benchmark vectors are verified E5 768-dimensional vectors. Preserve that disclosure in backup notes rather than silently editing the snapshot.

### Source footer

`huy-retrieval-report.vi.md`, §3.1–3.2; `docs/e5-production-rollout.md`.

## Slide 12 — Retrieval and Reranking Pipeline

### On-slide

**Original question → E5 dense retrieval**

**Question → VI/EN translation → BM25 lexical retrieval**

Both branches → RRF fusion → 30 candidates → BGE reranker → 10 chunks

- Apply access and document scope before candidate selection.
- BGE scores the original question against original chunk text.
- Reranking cannot recover evidence missing from the candidate pool.

### Visual

Use two parallel branches. Translation feeds the lexical branch; the original question feeds dense retrieval and BGE. Label the outputs “30 candidates” and “10 evidence chunks.” Avoid a sequential lexical → dense diagram.

### Speaker notes

Dense retrieval captures semantic similarity. Translated lexical queries add term matching across Vietnamese and English. Reciprocal rank fusion combines ranks rather than adding cosine and BM25 scores directly. BGE is a separate cross-encoder, not our embedding model. The main measured pipeline uses original chunk text, not the earlier narrative-context experiment. In this benchmark, target document language is verified. Production still defaults to ordinary hybrid; translated_hybrid_rerank is optional, and HTTP/UI does not yet provide the verified language mapping used in the experiment.

### Source footer

`huy-retrieval-report.vi.md`, §3.3–3.4; `docs/translated-hybrid-rerank.md`.

## Slide 15 — Experimental Setup and Reproducibility

### On-slide


| Control      | Recorded setup                                                       |
| ------------ | -------------------------------------------------------------------- |
| Corpus       | 10 simulated documents; 1,063 frozen chunks                          |
| Questions    | 20 intents × 2 query languages × 2 document languages = 80 cases     |
| Categories   | Narrative, table/numeric, multi-chunk, paraphrase: 5 intents each    |
| Models       | Pinned E5-base + BGE-v2-m3; pretrained                               |
| Runtime      | RTX 2060; FP32; BGE batch size 4                                     |
| Retrieval    | Candidate pool 30; final 10; five target-language documents          |
| Reproduction | Frozen inputs, translations, vectors, code, hashes, and saved scores |


**One pass per case/method; 80 cases are not 80 independent questions.**

### Visual

Use the table layout. Put exact commands, full model revisions, and manifest hash in a backup slide or linked report.

### Speaker notes

The earlier 48-case set is development evidence. New questions and labels were frozen before this run, but the simulated corpus was already known. Labels were assistant-authored and source-checked, not independently certified annotations. We used production SQL on temporary frozen tables. We did not measure three independent repeated runs; a training seed, learning rate, or optimizer does not apply to this pretrained inference experiment.

### Source footer

`artifacts/evaluation/heldout-review2-v1/protocol.json`; final SQL run `REPORT.vi.md`.

## Slide 16 — Evaluation Metrics and Scoring Protocol

### On-slide: Huy's retrieval rows


| Metric                | What it checks                                  |
| --------------------- | ----------------------------------------------- |
| Recall@10             | Fraction of annotated relevant chunks retrieved |
| MRR@10                | Rank of the first relevant chunk                |
| nDCG@10               | Ordering of relevant chunks                     |
| Full evidence@10      | All required evidence components present        |
| Component coverage@10 | Fraction of required components fully covered   |


**Accept annotated alternative passages and valid multi-chunk evidence.**

**Evidence coverage is not generated-answer accuracy.**

### Visual

Use a small “action + approver” example: retrieving only the action is partial coverage; retrieving both satisfies the full requirement. On the group's combined slide, retain only two or three retrieval rows so the other owners have space for measured OCR/generation/integration metrics.

### Speaker notes

Relevance is mapped through exact source-character spans. Retrieving a correct file or page is insufficient. A chunk can overlap one relevant span without supplying a complete answer, which is why we report full evidence separately. Valid alternatives can provide full evidence without retrieving every annotated relevant chunk, so full evidence and Recall are different measures. Annotation is not exhaustive. Generation and faithfulness metrics must come from the generation owner, not these retrieval numbers.

### Source footer

`huy-retrieval-report.vi.md`, §4; final run `metrics.csv` and `REPORT.vi.md`.

## Slide 17 — Baseline and Proposed-Method Comparison

### On-slide


| Method                      | Full evidence@10   | Recall@10  | MRR@10     |
| --------------------------- | ------------------: | ----------: | ----------: |
| Dense E5                    | 52/80 (65.00%)     | 0.6563     | 0.5586     |
| Dense E5 + BGE              | 62/80 (77.50%)     | 0.7875     | 0.8213     |
| Translated hybrid           | 63/80 (78.75%)     | 0.7917     | 0.6590     |
| **Translated hybrid + BGE** | **69/80 (86.25%)** | **0.8823** | **0.9000** |


**17 more complete cases than dense retrieval (+21.25 percentage points).**

### Visual

Use either this table or four bars for full evidence@10, with a 0–100% axis and numeric labels. Do not duplicate a dense table and a full chart on one slide. The template's “Answer Score” column should be replaced with “Full evidence@10” for this retrieval-only comparison; generation results belong in a separate measured comparison.

### Speaker notes

The proposed pipeline reaches 86.25% complete evidence on this benchmark. This does not mean the LLM answers 86.25% correctly. Relative to dense+BGE it gains eight cases and loses one, for a net gain of seven. These are two implemented experimental baselines, not proof that we have reproduced two research papers. Paper-versus-group comparison remains a separate group requirement.

### Source footer

Final run `review2-reviewed-r1-sql-20261022/REPORT.vi.md`, main comparison.

## Slide 18 — Ablation Study

### On-slide


| Controlled comparison                       | Complete evidence@10 |
| ------------------------------------------- | --------------------: |
| Dense → Dense + BGE                         | 52 → 62 / 80         |
| Translated hybrid → Translated hybrid + BGE | 63 → 69 / 80         |


**BGE adds six complete cases to translated hybrid, with no full-evidence regressions.**

Held fixed: corpus, labels, E5 vectors, scope, final k, and runtime.

**Not isolated here:** translation versus lexical retrieval/fusion.

### Visual

Use two before/after pairs. Do not invent “without translation” results for this 80-case benchmark. Historical controls from the 48-case development set must be clearly separated if included in backup.

### Speaker notes

These comparisons isolate the reranker within each candidate method. We cannot isolate translation because the new run lacks an original-query hybrid arm. For full evidence, intent-cluster bootstrap gives a 95% gain interval of 10–35 percentage points versus dense, but 0–20 versus dense+BGE. The latter touches zero, so we should avoid a broad statistical superiority claim. Bootstrap over twenty intents is not repeated inference or a substitute for independent labels.

### Source footer

`huy-retrieval-report.vi.md`, §5.1; final run report.

## Slide 19 — Latency, Model Size, and Resource Usage

### On-slide: retrieval measurements


| Method                  | Mean warm latency | p95      |
| ----------------------- | -----------------: | --------: |
| Dense                   | 546 ms            | 941 ms   |
| Dense + BGE             | 1,691 ms          | 2,416 ms |
| Translated hybrid       | 2,437 ms          | 3,165 ms |
| Translated hybrid + BGE | 3,609 ms          | 4,605 ms |


RTX 2060 · FP32 · BGE batch 4

**Excludes model startup, live translation API, and generation.**

### Visual

Keep this timing table on the slide. Put model files in a compact side note if space permits: E5 weights ≈1,061 MiB; BGE weights ≈2,166 MiB. These are cached weight-file sizes, not total installed size or VRAM.

### Speaker notes

Better retrieval costs more latency. The proposed method averages 3.609 seconds for the measured warm retrieval stages. Translation preparation separately averaged 0.560 seconds per query, but we did not measure live end-to-end response time and should not claim it by adding two stage averages. Peak allocated PyTorch memory was 2.212 GiB with sequential model loading, not simultaneous production residency or total GPU memory. No concurrency or cold-start benchmark is claimed. Add generation and application measurements only if the responsible owners have evidence.

### Source footer

Final run report, latency section; `docs/review2/retrieval-report-stats.json`.

## Slide 20 — Failure Analysis

### On-slide

**All 11 remaining failures lack evidence in the top-30 candidate pool.**


| Failure group           | Cases | Observed issue                               |
| ----------------------- | -----: | -------------------------------------------- |
| Records-retention query | 1     | Correct chunk: dense rank 19 → fused rank 33 |
| Product ID 19           | 2     | Required row outside the candidate pool      |
| Product IDs 1 + 3       | 4     | ID 3 missing from candidate pool             |
| Product IDs 8 + 9       | 4     | ID 9 missing from candidate pool             |


**Next: identifier-aware row lookup and multi-ID candidate merging.**

### Visual

Show a cutoff at rank 30: correct chunk at 33 → not seen by BGE. Keep “11/11 failures inspected” visible. This slide summarizes every final failure, not selected successes.

### Speaker notes

The records-retention query is a real regression relative to dense+BGE: translation terminology and fusion move its correct chunk outside the cutoff. We cannot attribute the cause entirely to translation without another ablation. For table joins, repeated headers and values do not guarantee that retrieval finds the correct Product ID row. Multi-chunk success is only 12/20. Increasing the pool from 30 to 50 cannot solve rows ranked beyond 200. These fixes are proposed after this result and have not been implemented or evaluated on this set.

### Source footer

Final run `candidate-diagnostics.json`; `huy-retrieval-report.vi.md`, §7.

## Slide 21 — Limitations and Threats to Validity

### On-slide: retrieval contribution

- Small, known simulated corpus; 20 paired intents.
- Assistant-authored labels; no independent annotation agreement.
- Six intents have identical VI/EN table evidence chunks.
- Verified target-language scope; production routing is not equivalent yet.
- One pass per method; incomplete translation/fusion ablation.
- Retrieval evidence does not establish generation correctness.

### Visual

Use the template's two columns: “Evaluation limits” and “System limits.” Merge these points with the other owners' limitations; keep only the highest-priority five or six in the shared slide.

### Speaker notes

The result is useful evidence for this controlled task, not a claim of generalization to all enterprises. The HTTP/UI language mapping differs from the controlled experiment. Context packing can remove evidence before generation, and a development diagnostic found a citation-validation issue requiring the generation owner's follow-up; this is not a measured hallucination rate. The team's proposed 50-page PDF remains future work, not part of this benchmark.

### Source footer

`huy-retrieval-report.vi.md`, §3.4, §4, §8.

## Contributions to shared slides

- **Slide 6:** evaluation corpus = 10 documents / 1,063 chunks / VI + EN / five formats. This is not the entire platform corpus. Workbook contributes 970 chunks (91.25%). Raw file size/page/source totals require the data owner's confirmation.
- **Slide 7:** describe actual label authorship and source checks. Do not fill Kappa without independent annotation measurements. Distinguish development questions from the pre-run frozen evaluation set.
- **Slide 5:** dense and dense+BGE are our measured controls. Add actual paper references and explain dataset/metric gaps with the research owner; no external paper scores are supplied here.
- **Slide 22:** retrieval conclusion: “Translated hybrid + BGE improved complete evidence from 52/80 to 69/80.” Next work: “Establish a frozen baseline on the new PDF; evaluate identifier-aware candidate retrieval on separate validation questions.” Owner: Huy; schedule to be agreed. Do not promise a finished PDF or new results.

## Suggested five-minute speaking route

Do not read every row. These ten pages share the group's slide allocation; other owners may speak on the shared evaluation pages.


| Part         | Target time | Key message                                   |
| ------------ | -----------: | --------------------------------------------- |
| Slides 10–11 | 45 s        | Compatible tokenization and E5 index          |
| Slide 12     | 45 s        | Two candidate branches, then reranking        |
| Slides 15–16 | 45 s        | 20 intents, four directions, exact evidence   |
| Slides 17–18 | 70 s        | 52 → 69 cases; what is and is not isolated    |
| Slide 19     | 30 s        | Quality/latency trade-off and timing boundary |
| Slides 20–21 | 65 s        | Candidate misses, limitations, next work      |


Practice with the group; five minutes here is a planning estimate, not an agreed review duration.

## Backup references

- [Detailed report](huy-retrieval-report.vi.md)
- [Vietnamese speaking notes and Q&amp;A](huy-speaking-notes.vi.md)
- [Token/model resource facts](retrieval-report-stats.json)
- [Benchmark entry](../../artifacts/evaluation/heldout-review2-v1/RESULTS.vi.md)
- [Final measured report](../../artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md)

This file provides paste-ready content. The Canva design/PDF has not been edited, and no replacement PPTX is created.