# Four-direction multilingual dense retrieval — 2026-10-18

Two original reports, 118 pages, 525 shared chunks, 24 paired intents / 48 queries. Original two-document scope rebuilt locally; Supabase unchanged. All three cached models ran offline on RTX 2060, float32, normalized cosine top ten. No BM25, query translation, reranking, generation or inference API. Both reports compete for every question; language labels group results only.

## Main result: evidence-page recall in top ten chunks

| Query → evidence document | Cases | E5-base multilingual | BGE-M3 | Qwen3-0.6B |
| --- | ---: | ---: | ---: | ---: |
| Việt → Việt | 10 | 80.00% (8/10) | 80.00% (8/10) | 70.00% (7/10) |
| Anh → Anh | 12 | 41.67% (5/12) | 41.67% (5/12) | 41.67% (5/12) |
| Việt → Anh | 12 | 66.67% (8/12) | 41.67% (5/12) | 50.00% (6/12) |
| Anh → Việt | 10 | 10.00% (1/10) | 80.00% (8/10) | 70.00% (7/10) |
| Four-direction macro (equal direction weights) | 44 queries | 49.58% | 60.83% | 57.92% |

Two mixed-document intents (four queries) are excluded from this four-direction macro and reported separately below. These are 24 paired intents, not 48 independent questions. The same-language and cross-language query variants use identical gold evidence.

The initial 100-word chunk attempt is retained under preflight-100-word-attempt/ but excluded from this report: Qwen rejected 11 chunks over 512 tokens. All three models were rerun on the same final 60-word / 12-word-overlap corpus after an all-model token preflight.

## Meaning and limits

Scoring checks whether the top ten chunks include each labelled evidence page, counting repeated hits on one page once. It does not prove the selected chunk contains the answer; page coverage is coarser than passage relevance. Other valid evidence pages may be unlabelled. Do not compare these percentages directly to the previous 249-chunk financial benchmark or VietStyle source-file coverage.

The English document is PVFCCo; the Vietnamese document is Long Hau. Different topics, document lengths and OCR quality confound language-only conclusions. Long Hau was reconstructed with local Tesseract vie+eng at 200 DPI, PSM 3; English pages use native text where available. Two English pages (2, 95) yield no text, and no gold page is empty. Old scanned/OCR noise and flattened tables remain. Four-direction sample sizes are only 10 or 12; one case shifts a score by 8.33 or 10 percentage points.

## Mixed-document cases

| Query language | Cases | E5-base | BGE-M3 | Qwen3-0.6B |
| --- | ---: | ---: | ---: | ---: |
| vi->mixed | 2 | 25.00% | 25.00% | 50.00% |
| en->mixed | 2 | 25.00% | 0.00% | 50.00% |

## Changes from the previous code

- Added scripts/retrieval/prepare_four_direction_benchmark.py: extracts/OCRs complete original PDFs and saves pages, common 60-word chunks with 12-word overlap, hashes, bilingual cases and old-evidence validation. Before, only partial historical retrieved contexts were available; these are now validation inputs only. Original PDF files with two different Vietnamese filenames have identical SHA256.
- Extended evaluate_embedding_candidates.py score_case and summary: cases with gold_pages get deduplicated page recall and reciprocal rank, grouped by direction. Existing VietStyle source-file scoring is retained. No language-based retrieval filter was added.
- Added one focused check for duplicate page hits and document identity; all four runner unit checks passed. No additional changes to embedding_service.py or the live database.

## Validation and reproducibility

All 144 top-ten orders, page-recall values and reciprocal ranks were independently recomputed from saved passage/query vectors. All matrices are finite, normalized, and hash-matched to identical frozen chunks/cases; every extracted page word is covered by the common chunks. All prefixed model inputs fit cap 512 without truncation. Model revisions and required prefixes/instructions are recorded in each candidate config. Local timing excludes model load and SQL/network; batch sizes differ (E5/BGE 2, Qwen 1), so timings are not a controlled speed ranking. Historical page evidence is retained; original chunk IDs are not reused. Evidence-validation token overlap is diagnostic, not a proof of answer correctness; the noisy old English cover was checked against its clean native title/company/year.

```bash
.venv/bin/python scripts/retrieval/prepare_four_direction_benchmark.py
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/four-direction-20261018 --model multilingual-e5-base --revision d128750597153bb5987e10b1c3493a34e5a4502a --device cuda --batch-size 2
```

Use bge-m3 or qwen3-embedding-0.6b and their recorded revisions for other models; Qwen batch size 1. Existing outputs are protected: choose a fresh --output-dir for repeat runs. Preparation requires local Tesseract eng/vie plus PyMuPDF and the retained-original-contexts.json included with this snapshot. No new Python dependency was installed.

## Per-query evidence-page recall

| Case | Direction | E5-base | BGE-M3 | Qwen3-0.6B |
| --- | --- | ---: | ---: | ---: |
| Q01-vi | vi->en | 0% | 0% | 0% |
| Q01-en | en->en | 0% | 0% | 0% |
| Q02-vi | vi->en | 100% | 100% | 100% |
| Q02-en | en->en | 0% | 100% | 100% |
| Q03-vi | vi->en | 0% | 0% | 0% |
| Q03-en | en->en | 0% | 0% | 0% |
| Q04-vi | vi->en | 100% | 100% | 100% |
| Q04-en | en->en | 100% | 100% | 100% |
| Q05-vi | vi->en | 100% | 100% | 100% |
| Q05-en | en->en | 100% | 100% | 100% |
| Q06-vi | vi->en | 100% | 0% | 0% |
| Q06-en | en->en | 0% | 0% | 0% |
| Q07-vi | vi->en | 100% | 0% | 0% |
| Q07-en | en->en | 0% | 0% | 0% |
| Q08-vi | vi->en | 100% | 100% | 100% |
| Q08-en | en->en | 100% | 100% | 100% |
| Q09-vi | vi->en | 100% | 0% | 100% |
| Q09-en | en->en | 100% | 0% | 0% |
| Q10-vi | vi->en | 100% | 100% | 100% |
| Q10-en | en->en | 100% | 100% | 100% |
| Q11-vi | vi->en | 0% | 0% | 0% |
| Q11-en | en->en | 0% | 0% | 0% |
| Q12-vi | vi->en | 0% | 0% | 0% |
| Q12-en | en->en | 0% | 0% | 0% |
| Q13-vi | vi->vi | 100% | 100% | 100% |
| Q13-en | en->vi | 100% | 100% | 100% |
| Q14-vi | vi->vi | 100% | 100% | 100% |
| Q14-en | en->vi | 0% | 100% | 100% |
| Q15-vi | vi->vi | 100% | 100% | 100% |
| Q15-en | en->vi | 0% | 100% | 100% |
| Q16-vi | vi->vi | 0% | 0% | 0% |
| Q16-en | en->vi | 0% | 0% | 0% |
| Q17-vi | vi->vi | 0% | 0% | 0% |
| Q17-en | en->vi | 0% | 0% | 0% |
| Q18-vi | vi->vi | 100% | 100% | 100% |
| Q18-en | en->vi | 0% | 100% | 100% |
| Q19-vi | vi->vi | 100% | 100% | 100% |
| Q19-en | en->vi | 0% | 100% | 100% |
| Q20-vi | vi->vi | 100% | 100% | 100% |
| Q20-en | en->vi | 0% | 100% | 100% |
| Q21-vi | vi->vi | 100% | 100% | 0% |
| Q21-en | en->vi | 0% | 100% | 0% |
| Q22-vi | vi->vi | 100% | 100% | 100% |
| Q22-en | en->vi | 0% | 100% | 100% |
| Q23-vi | vi->mixed | 50% | 0% | 50% |
| Q23-en | en->mixed | 0% | 0% | 50% |
| Q24-vi | vi->mixed | 0% | 50% | 50% |
| Q24-en | en->mixed | 50% | 0% | 50% |
