## 2026-10-23 - PC resume: slides and new document checkpoint

User requested commit/push to Huy before switching to PC. Read the current
commit ID from git log; this entry supersedes earlier local/uncommitted notes.

NEXT TASK: finish the shared Canva Review2 presentation. The23-slide template
is on Canva; laptop export was C:/Users/Eroz/Downloads/Review 2.pdf, not tracked.
Paste-ready English Huy content is docs/review2/huy-canva-content.en.md.
Latest discussion: members used different datasets/hardware/metrics, so give
parsing/OCR, retrieval and generation their own experiment setup/results pages;
combine setup+metrics where useful to stay within18–25 main slides. Don't imply
cross-machine latency is a controlled comparison. Architecture/limits/next
steps can stay shared. User needed help with slides10,12,15: keep text short,
move detailed configs/hashes to backup. Proposed method does NOT mean tuning:
our measured proposal combines pretrained E5, translated BM25, RRF and BGE;
no new model/algorithm invention or fine-tuning claim.

Use existing reviewed-r1 80-case result for Review2:69/80 complete evidence@10,
86.25%, NOT generated-answer accuracy. No new benchmark is needed just to fill
slides. Finish demo readiness/coordinate other members' measured evidence.
After Review2, freeze reviewed new inputs, run current system unchanged, then
tune candidate retrieval on separate development questions.

NEW DOCUMENTS INCLUDED: artifacts/datasets/README.md points to Bảo An (50pages,
30 draft bilingual intents) and user's translated VietStyle (54physical pages,
50policy pages, DOCX/PDF). They are different policies. Do not transfer Bảo An
labels to VietStyle. Both user-created ZIP archives match their folders; root
artifacts/datasets.zip contains only Bảo An, datasets/vietstyle-operations-vi-v1.zip
contains VietStyle. Original English download and Canva export stay outside
repo on laptop. VN files work directly on PC; rebuilding translation needs the
original English DOCX. PDF generation scripts use Windows Arial/Word; don't
assume they run unchanged under WSL. Existing outputs do not need rebuilding.

Before checkpoint: dataset manifests and both ZIP contents/hash matches checked,
text scanned for likely credentials, no likely matches. Added -text attributes
for dataset and generator bytes to preserve manifest hashes on PC/WSL. No new
retrieval/generation inference, API calls, DB writes or regression tests.

## 2026-10-23 - User's downloaded VietStyle policy translated to Vietnamese

User supplied English `VietStyle_Enterprise_Operating_Policy_v1.0.docx` and PDF
in C:/Users/Eroz/Downloads and requested conversion to Vietnamese. Created
`artifacts/datasets/vietstyle-operations-vi-v1/` with VN DOCX/PDF/Markdown,
paragraph translation TSV/alignment, README, verification and hashes. Source
English files unchanged. This is separate from Bảo An; it preserves the user's
source policies, not the synthetic handbook's thresholds.

All1228 paragraphs/56 tables retained; all1174 nonempty paragraphs/identifiers
appear in PDF after whitespace normalization. PDF still54 physical pages,
50 numbered policy pages plus front matter/appendices. Numeric comparison
matches apart from three date translations adding numeric month10/12 where
English spelled October/December. Sample six pages visually inspected.
Installed Word exported PDF via COM outside sandbox after sandbox session
failed; hidden automation instance closed in finally. No external API, model,
DB access, benchmark inference or regression tests. Translation does not
independently validate source legal/technical assertions or fix inconsistencies.

Builder: scripts/evaluation/translate_vietstyle_policy.py; paragraph-index
mapping requires original source DOCX. Bảo An question labels cannot simply
be reused against VietStyle: policies differ. Prepare separate reviewed labels
before benchmarking. All new deliverables local/uncommitted; no push requested.

## 2026-10-23 - New 50-page Vietnamese synthetic PDF generated

User requested a single50-page document meeting the earlier operations-handbook
criteria and chose "Vietnamese document; Vietnamese/English questions" via async
reply. Created `artifacts/datasets/bao-an-operations-vi-v1/`; start README.md.
PDF `bao-an-operations.vi.pdf`: exactly50 A4 pages,48 digital and2 image-only
grayscale form pages43–44 (~173DPI). Fictional Bảo An policies/people/events;
different thresholds from older VietStyle, HR/procurement/warehouse/IT, mixed
tables/prose, similar item IDs, exception boundaries, matrix across47–48.
Source is source.json + handbook.vi.md; generators under scripts/evaluation/.

Separate questions.draft.json/REVIEW.md contain30 intents,60VI/EN texts,
26answerable and4unanswerable. Target documents VI only: two query-language
directions, not four. Labels have exact segment-local Unicode evidence,
requirements/alternatives and draft answers; NOT old evidence-v3 parser offsets.
Independent review and alternative-source expansion remain pending. Source and
questions were co-authored: controlled synthetic challenge, not independently
held-out evidence. Review.csv includes a human checklist.

Validated exact50 pages, digital/scan separation, font glyphs, all digital
segment text against extraction after whitespace/separator normalization, layout
bounds and evidence selectors. Sampled six pages visually (cover, thresholds,
item table, scan, continued matrix). Fixed Arial Unicode aliases so hyphens,
spaces and semicolons extract as authored; fixed goods/IT-scope ambiguity before
final generation. Scan OCR accuracy not measured. No models/API/DB calls or
benchmark/regression tests. manifest.json hashes outputs and generator sources.

For future PDF/OCR experiments ingest ONLY the PDF: source.json/Markdown include
scan transcriptions; indexing them would bypass OCR and leak evaluation sources.
Questions/answers/review files must also stay out of index. Freeze reviewed
version before unchanged-baseline run, then tune on separate development cases.
Existing frozen benchmark untouched; no new results for Review2 slides.
User's Canva content and this dataset remain local/uncommitted, no push done.

## 2026-10-23 - Canva template reviewed; Huy's English slide content prepared

User created the shared template in Canva and exported
`C:/Users/Eroz/Downloads/Review 2.pdf` (23 slides). Read its text and the newly
downloaded mixed training/RAG checklist. No visual-layout audit performed.
User agreed to use existing benchmark evidence for Review2, defer tuning, and
proceed with slides. Team's single 50-page PDF is still a future proposal;
topic/language and contents are not agreed, no document or benchmark exists.

Created `docs/review2/huy-canva-content.en.md`: paste-ready English text,
suggested visuals, speaker notes and evidence references for template slides
10–12 and15–21, plus contributions to shared6/7/5/22 and an estimated five-minute
speaking route. Uses reviewed-r1 80-case results and measured RTX2060 timing;
discloses annotation/scope/ablation limits and separates retrieval from answer
accuracy. Production measured pipeline uses original chunks, not historical
narrative-parent experiment. No new experiments, inference, API/database calls,
model downloads or tests. Canva PDF/design not edited; no PPTX created.
Next: user pastes/adapts content in Canva, coordinate shared pages/remaining
generation/data/deployment evidence with teammates, review readability once
filled. Prior "no template exists" entry below describes an older state.
New content and this handoff update are local/uncommitted.

## 2026-10-23 - Laptop handoff: Review 2 slides next

User is going outside and explicitly requested writing this handoff, committing and pushing to Huy. Previous completed checkpoint is `0cd149b` (already pushed); older entries saying uncommitted/unpushed describe historical states, not the current checkpoint.

### Start here on the laptop

- Pull branch Huy after saving any laptop changes; inspect git status first and do not overwrite local work.
- Main task now: design a shared English-language Review 2 slide template for the whole group. Each member fills their section. User wants slide design before any new approximately 100-page PDF experiments.
- User requested a copy-paste prompt for ChatGPT; it was supplied in the conversation. No usable PPTX/PDF/template has been created or saved in the repository. A Canva generation attempt produced an empty single-page design; do not describe it as completed. No pending Canva editing transaction remains.
- Keep the frozen evidence, questions, vectors and benchmark results unchanged. No additional benchmark, model tuning, production changes, API calls or database writes are needed for the slide handoff.

### Slide brief already agreed

All slide text and placeholders should be English. Shared whole-group template, editable PPTX (optional PDF preview), 16:9, white/navy/teal, Arial or another portable font, titles 36-44 pt, body 22-28 pt, table/caption preferably at least 18 pt. Editable diagrams/tables; section-owner and source placeholders; speaker notes explaining what to fill. No invented results, citations, training curves, deployment/CI claims or repeated-run statistics.

The prompt proposes 23 slides: title; roadmap; problem/motivation; objectives/scope; related work/baselines/gap; dataset overview; data preparation/quality/annotation; architecture; parsing/OCR; tokenization/chunking/provenance; embeddings/index; retrieval/reranking; grounded generation/agents; integration/deployment; experimental setup/reproducibility; metrics/scoring; method comparison; ablation; latency/model size/resources; failure analysis; limitations; conclusions/next steps; Q&A.

Distinguish the proposed design from source requirements. The previously read Review 2 checklist calls for 18-25 slides and coverage of data, related methods/baselines, architecture/method, experiments/metrics, comparisons/ablation, failures and feasibility. Training-specific items apply only if training was actually performed. Three-seed mean/std and annotation agreement must not be claimed unless actually measured. Re-open `docs/review2/review2-task2-checklist.docx` to confirm exact wording, including English-language requirements, before stating something is mandatory. The user recalls the presentation language is English and has requested English slides regardless.

### Authoritative files and numbers

- `docs/review2/huy-retrieval-report.vi.md`: Huy's detailed report section.
- `docs/review2/huy-speaking-notes.vi.md`: approximately five-minute speaking outline/Q&A.
- `docs/review2/presentation-plan.md`: group outline, not an actual slide deck.
- `docs/review2/retrieval-report-stats.json`: measured token/model/resource facts.
- `artifacts/review2/README.md`: navigation for Review 2.
- `artifacts/evaluation/heldout-review2-v1/RESULTS.vi.md`: main benchmark entry.
- `artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md`: full final report.

Main benchmark: 20 intents x 2 query languages x 2 document languages = 80 cases, not 80 independent questions. Frozen simulated corpus 1,063 chunks / 10 documents, controlled five-document target-language scope. E5 `intfloat/multilingual-e5-base` + BGE `BAAI/bge-reranker-v2-m3`, RTX 2060, production SQL on temporary tables. Full evidence@10: dense 52/80 (65%); dense+BGE 62/80 (77.5%); translated hybrid raw 63/80 (78.75%); translated hybrid+BGE 69/80 (86.25%). Final Recall@10 .882292, MRR@10 .900000, nDCG@10 .863527, P@10 .13375. Mean/median/p95 warm retrieval latency 3609/3578/4605 ms. Translation API preparation mean approximately .560 s per query is separate; generation was not benchmarked. Old 48-case 100% result is development evidence, not the headline result.

All 11 final losses lack required evidence in the top-30 candidate pool before reranking: H04 VI-to-EN (1), H08 target VI (2), H11 (4), H14 (4). Table/multi-row cases remain a limitation. No original-query hybrid arm in the new 80-case run, so do not attribute all gains solely to translation. Assistant-authored/source-checked labels are not independently certified human annotations. Optional offline adapter has tie-order differences; use default SQL backend for reproducing the recorded result.

Frozen corpus JSONL has stale Qwen model metadata from preparation; actual frozen vectors are verified E5 768-dimensional. Report discloses this; do not silently rewrite frozen files. Cached E5 token audit including prefix/special tokens: 449,203 total, longest 476/512, zero overlength. Production default retrieval method remains ordinary `hybrid`; opt in to `translated_hybrid_rerank`. HTTP/UI still does not supply verified document-language mapping. These are relevant limits when describing production readiness.

### Verification and git transport

For artifact replay (not a fresh inference run):
`.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022`

Use Linux git for local status/staging/commit. Git for Windows on the WSL UNC path can report apparent modifications for Linux files; Linux git is authoritative for this checkout. WSL HTTPS git lacks credentials on this desktop. Existing Windows Git Credential Manager can fetch/push using Git for Windows with per-command `safe.directory` for `//wsl.localhost/Ubuntu/home/eroz/projects/enterprise-knowledge-ai-agent` and `credential.helper=manager`; no global configuration edits or token printing. Laptop authentication may differ.

This handoff changes documentation only; no new inference or production behavior. Latest commit ID can be obtained from git log after committing this entry.

## 2026-10-22 — Review2 report completed and checkpoint validated

User authorized saving the work milestone and writing Huy's section. Added docs/review2/huy-retrieval-report.vi.md (tokenization, E5/schema, pipeline,80-case results, latency, all11 losses, limitations and reproducibility), huy-speaking-notes.vi.md (~5min speaking outline/Q&A), and retrieval-report-stats.json. Updated group presentation-plan to use80case/RTX2060/86.25% as main, old48case development as historical, and added navigation from artifacts/review2/README.md.

New report-only tokenizer audit (cached, no inference/API): VI224845 andEN224358 prefixed/special-token inputs,total449203; longest476/512, zero overlength. Actual E5 document vectors SHA25696a9ab9cbd5c624d19f51f28890223272b19d3c29e58dddf3024b359e50fa663 match original E5 candidate. Frozen corpus row metadata still labels prior Qwen model/token counts; report explicitly distinguishes stale source-preparation metadata from actual E5 vector manifest and freshly counted E5 tokens. Do not edit frozen files to hide this provenance limitation.

Cached weight files E5=1060.68MiB, BGE=2165.86MiB. Recorded Torch peak2.212GiB from sequential loading, not production co-resident models/all desktop VRAM. No extra benchmark/model inference, API calls or production source edits made for this report.

WSL Git had no HTTPS credentials. Existing Windows GCM account EroEroz successfully fetched Huy via Git for Windows with per-command safe.directory/credential.helper only, no global config change or token printing. Use that transport to push the authorized checkpoint. Validation before checkpoint:10 targeted metric/replay tests +3 bundle tests passed; final80-case artifact replay passed; documentation links/fences passed. All frozen benchmark and85 archived file hashes also verified against staged git blobs. Copied frozen code/CSV whitespace kept byte-identical; authored code/docs whitespace check passed. No likely token/credential patterns found in staged text. Final commit ID is obtained from git log, not a self-referential value in this file.

## 2026-10-22 — Artifact navigation/archiving completed

User authorized organizing artifacts. Added artifacts/README.md, review2/README.md, evaluation/README.md, archive/README.md, inventory-20261022.csv and cleanup-20261022.json. Reference scan covered1,048 source/notebook/data/doc files and280 direct evaluation entries. Archived79 unreferenced historical JSON plus main-review-20261021 and retrieval-metrics-20261022-initial (81 top-level entries, all contents SHA256 verified). No files deleted. Updated the initial-report link in development metrics REPORT and old handoff destinations. Production source and all frozen heldout files/manifest unchanged.

Archive map/hashes are in cleanup-20261022.json; restore only if old destinations are free. Existing corpus/vector/translation bundles and helpers with location-dependent root discovery stay in evaluation to preserve reruns. Remaining team OCR/generation reports were kept when referenced or portability unknown. Root docs make clear that archiving improves navigation, not disk usage. Current Review2 benchmark remains at evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022; use default SQL backend for reproducibility. All changes still uncommitted/unpushed.

## 2026-10-22 — Reviewed heldout benchmark completed (80/80, SQL/CUDA)

User approved replacing H10 with SOP, clarifying H19 and shortening H13, then running benchmark; explicitly consented via async question to send40 new simulated question texts to Groq. Completed all authorized work; no commit/push requested or performed.

Folder: `artifacts/evaluation/heldout-review2-v1/`. Start `RESULTS.vi.md`; full report/metrics/case failures in `runs/review2-reviewed-r1-sql-20261022/REPORT.vi.md`. Version reviewed-r1, manifest SHA256 **3f424cac026e098fb2cff98c03137e74e61cf48b7e4a219c503312a60b1a6a14**. Draft archived `history/draft-before-approved-edits.zip`; assistant review/audit describe old draft, not remaining H10 errors.

Changes: H10 now asks no-variance SOP table actions/approver (close ticket + retain audit trail + Warehouse Supervisor), accepting exact table/body duplicates in SOP VI/EN. H13 shorter with same labels, prior Q20 approval overlap disclosed. H19 asks whether code assigned + feedback departments, not unspecified code values. Synced questions/cases/evidence/authoring specs/REVIEW/overlap and refroze BEFORE inference.61 requirements/148 spans;20 intents/40texts/80cases. Source+empty oracles40 pairs, multi-chunk10,3 unittest checks, tokenizer50 E5 query /521 conservative BGE pair all passed. No human-certified annotation claim.

Groq40/40 translations succeeded; prepared/ checkpoint+manifest frozen, API mean.560s. No labels/documents sent; no later translation corrections. Run used cached E5/BGE on RTX2060 FP32 batch4, production SQL on TEMP frozen1063chunks10docs, scope5 target-language docs/admin. No public Supabase writes or model downloads. All80 cases completed; saved logits/rankings/metrics/evidence replay verified.

ALL80 metrics P@10 /R@10 /MRR@10 /nDCG@10; full evidence; mean/median/p95 ms:
- Dense .09625/.65625/.558591/.559436;52/80(65%);546/488/941ms.
- Dense+BGE .11875/.7875/.82125/.773126;62/80(77.5%);1691/1549/2416ms.
- Translated hybrid raw .11875/.791667/.658993/.669387;63/80(78.75%);2437/2370/3165ms.
- Translated hybrid+BGE .13375/.882292/.900000/.863527;69/80(86.25%);3609/3578/4605ms.
Final components208/244; macro coverage.89375. P@10 label ceiling15.5%. Gain vsdense+21.25pp cluster-bootstrap20 intents CI[10,35]; vsdense+BGE+8.75pp CI[0,20]. No original-query hybrid arm in new set, so BM25/fusion/translation effects aren't isolated. Only E5 embedding tested in this run.

Final language full cases: VI→VI17/20;VI→EN17/20;EN→VI17/20;EN→EN18/20. Categoryfull: narrative19/20,table18/20,multi12/20,paraphrase20/20. Final improves8 cases vsdense+BGE, regressesH04 VI→EN only. Reranker rescues6 fromraw hybrid, zero full-evidence regressions vsraw.

All11 final failures are missing from pool30 before rerank: H04 VI→EN1, H08 targetVI2, H11all4, H14all4. Verified with fresh productionSQL TEMP read using saved vectors/cache:11/11 exact top30 parity (`candidate-diagnostics.json`). H04 correctdense rank19, lexical absenttop300, fusion33; translation uses “file categories/storage” for “records/retention”. H08 goldlexical46/68→fusion84/72. H11Product3fusion211–354; H14Product9fusion42–200. Suggest future identifier/row-aware retrieval, multi-ID candidate joins, translation terminology. No tuning applied to this heldout set after results.

IMPORTANT offline limitation: diagnostic adapter top30 matchedSQL only1/11 failedcases (`offline-adapter-diagnostics.json`). OfflineBM25 ties break by string chunkID, SQL by numeric rowID; table ties affect ranks. Main benchmark and full rerun verified on SQL, unaffected. **Use default --backend sql to reproduce these scores**; don't claim optionaloffline equal or mix latency. No full offline80 inference performed or frozen code altered to tune after results.

Recheck artifacts:
`.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py verify-run artifacts/evaluation/heldout-review2-v1/runs/review2-reviewed-r1-sql-20261022`
Fresh rerun with same prepared inputs:
`.venv/bin/python artifacts/evaluation/heldout-review2-v1/run.py run --name review2-reviewed-r1-sql-repeat-02`

Keep inputs/code/prepared/runs together. Warm-stage latency excludes live API translation/generation/model startup; generation/faithfulness/RBAC/OCR not measured. New set uses known simulatedcorpus and6 whole-identical VI/EN table evidence chunks; don't claim unseen-domain or pure cross-language proof. Earlier Oct22 dev metrics/reports/docs remain uncommitted. Only tracked-file diff is handoff; production source unchanged.

## 2026-10-22 — Assistant source review of heldout questions

User requested review while studying. Added `heldout-review2-v1/ASSISTANT_REVIEW.vi.md` (3-minute priority list, all20 dispositions, bilingual rewrite suggestions) and `assistant-review-audit.json`. Frozen draft/questions/labels/manifest remain unchanged; no retrieval inference, translations, API calls, commits or pushes.

Important findings before first benchmark:
- H10: VI timing alternative H10.timing.vi.a0 at Manual parser5 [547,569) only says check inventory etc before PO issuance, not exceptional-PO approval timing. Actual approval table VI13/EN14 is valid. Label-only diagnostic using correct table alone gives VI Recall.5/nDCG.6131 vs EN Recall1/nDCG1 with full evidence1 for both. Remove invalid alternative if retaining question; preserve table spans. H10 repeats facts explicitly present in old Q20.exception_approval (optional) and a larger old Q20.human_approval bundle. Recommend replacement if requiring new facts.
- H19: wording “mã hóa ra sao” can imply exact reason code values; source only requires assigning a reason code, no codebook. Proposed VI/EN rewrite asks whether a code must be assigned + departments.
- H13: valid 2-chunk join, but ordinary Planner→Procurement approval already in Q20; supplier information/frequency new. Suggested shorter wording.
- Eight table-number intents keep English field labels and identical answer rows VI/EN; six H06/H07/H08/H11/H12/H14 have whole identical evidence chunks, H09/H15 KPI chunk differs in notes. Separate table vs prose results; avoid claiming all80 are pure cross-language tests.
- Evidence source coverage: Manual13 intents, XLSX9, Deck3, Registry1, SOP PDF0 (overlapping counts). No no-answer/RBAC/generation/OCR measurement. Full evidence and Recall differ with valid alternative sources; report explains H02/H13/H15/H18.
- No edits applied to frozen inputs; assistant review is not human signoff. User can inspect only H10/H19/H13 and the report's priority section. If revising before inference, preserve draft, sync all question/case/evidence views and authoring specs, regenerate manifest/map, then verify/tests. Do not mark reviewer Huy unless he actually approves.

## 2026-10-22 — New pre-results retrieval question set (heldout-review2-v1)

User requested a separate new question set, existing proposal/Review 2 retrieval metrics, and one folder for reruns/results. Created `artifacts/evaluation/heldout-review2-v1/`; start with its README.md and REVIEW.md.

- 20 new intents (5 narrative, 5 table/numeric, 5 two-chunk, 5 paraphrase), VI/EN = 40 texts / 80 directional cases. Same previously seen simulated corpus; assistant-authored, related-development-topic audit provided. Human review PENDING; do not claim independent annotator validation or unseen-domain generalization.
- 60 required evidence components / 141 exact source spans. Full/empty source oracles passed all 40 intent/language pairs; 10 two-chunk checks confirm one chunk insufficient and a pair sufficient. No retrieval/model inference on new questions yet.
- Frozen self-contained corpus/vector/parser/PG lexeme snapshots, pinned E5/BGE/model/code revisions and SHA-256 manifest. Uses cached local E5 + BGE, no production-code change or public DB writes.
- `run.py verify` validates inputs; `review --reviewer NAME` records operator self-report only after actual review; `prepare --allow-groq` FUTURE opt-in sends 40 new simulated question texts (not labels/documents) and extracts query lexemes read-only; `run --name NAME` creates results beneath runs/NAME, default production SQL on temporary frozen tables; optional --backend offline must be reported separately. `verify-run FOLDER` replays stored logits/metrics, not fresh inference.
- Groq not called for this set. Prior consent covered 24 older questions, not these 40; obtain consent before calling prepare. No benchmark scores/results claimed for this set. Runs/ and prepared/ currently empty placeholders.
- 3 standard-library tests passed (source/two-chunk oracle, frozen-file tampering, synthetic score/ranking replay + corruption/missing-method detection). `test_bundle.py` runs without pytest. Tokenizer-only local-cache preflight passed; see tokenizer-preflight.json. No downloads.
- Metrics: P/R@10, MRR@10, nDCG@10, full/component evidence@10, mean/median/p95 warm retrieval latency, grouped by language direction/category. Excludes generation and API translation time; historical preparation API times stored separately. Query encoding measured once per 40 unique texts and reused for two target-language cases. No ROUGE/faithfulness claims.
- User should review REVIEW.md before the first inference run. Keep prior development sets and Oct22 metrics/latency reports. This work is uncommitted/unpushed.

# Handoff for Codex on another machine

Updated: 2026-10-22, Asia/Saigon. Read this before continuing the user's work.

## Latest: supplemental metrics, GPU timing and downside report, 2026-10-22

User requested more benchmark metrics/evidence and analysis of downsides before
Review 2. Used Ponytail workflow: reuse frozen rankings/scorer; no label/question
edits or new model downloads/API calls. Added two evaluation-only scripts:
- scripts/retrieval/evaluate_fresh_retrieval_metrics.py
- scripts/retrieval/benchmark_fresh_stage_latency.py
and tests/test_fresh_retrieval_metrics.py. Production code/index unchanged today.

Canonical report: artifacts/evaluation/retrieval-metrics-20261022/REPORT.vi.md;
slide table: SLIDE_SUMMARY.vi.md; JSON/CSV/qrels include all 48 cases x6 methods.
Initial analysis is preserved under artifacts/archive/retrieval-metrics-20261022-initial, including
its evaluator snapshot; canonical version additionally probes context for every
ablation. Frozen source hashes/manifest unchanged; original replayers verified.

Primary results (P@10/R@10/MRR@10/nDCG@10, full evidence):
Dense .1000/.802083/.618948/.656541,39/48,91/112 components;
Dense+BGE .11875/.947917/.958333/.950274,46/48,107/112;
Translated hybrid+BGE .125/1/.989583/.990639,48/48,112/112.
Additional controls BM25 original39/48; identity-query hybrid41/48; translated
hybrid without BGE47/48. Identity hybrid uses production translated-hybrid fusion
with identity queries and frozen lexemes, not a separate legacy SQL baseline.
Qrels are any exact mapped non-whitespace overlap with required evidence,
including partial spans and OR alternatives; unjudged treated nonrelevant but
labels are not exhaustive. 18 intent/language gold sets have1 chunk,6 have2;
P@10 annotated ceiling is12.5%, not evidence that87.5% context is wrong.

GPU timing fully completed48 cases x3 arms on cached RTX2060/FP32/batch4. Uses
session-local TEMP documents/document_chunks tables with1063 frozen chunks and
real production SQL; rollback on close, no writes to public production tables.
All144 new top10 rankings exactly match frozen outputs; integrated selector
smoke passed. See retrieval-latency-20261022/{results,run-provenance,
live-frozen-parity}.json. Median/p95 warm E5+SQL+BGE stages: dense0.533/0.988s;
dense+BGE1.441/1.899s; translated+BGE3.420/4.166s. API translation replayed from
cache, not timed as real API; generation/UI/concurrency excluded. One pass over
48 cases, not multi-seed latency certification. Model init+warmup75.3s; PyTorch
peak allocated3.25GiB, not total device/process memory. No truncation.

Downsides: hybrid without translation EN->VI7/12 vs dense8/12 (F01 regression).
F12 EN->VI nDCG1->.91972 due gold ranks1,2->1,3, without evidence regression.
F03 VI->EN untranslated-hybrid gold2->translated gold4 before BGE. Known F08
stock->financial-shares translation error remains. Cluster bootstrap resamples
12 paired intents, not48 independent questions; +2 full cases has95% interval
[0,+10.42]percentage points. Development/synthetic/oracle-language-scope limits
remain; do not claim production100% accuracy or independent generalization.

Actual RAG context packing with provider/cache mocked: dense loses3 initially
complete cases; raw translated hybrid loses F08 EN->VI (47/48 top10 ->46/48
packed). Dense+BGE stays46/48; translated+BGE stays48/48. Not generation scoring.
NEW BUG FOR AN: controlled synthetic probe at actual5000-char cap shows an answer
citing S2 is accepted after S2 was removed from prompt; validator uses original
contexts instead of prompt_contexts. See citation-validation-probe.json and
reproduce_citation_validation.py. This is not a real-LLM failure rate. Not fixed
in production during this benchmark-only task; coordinate with An before demo.

16 targeted metric/evidence replay tests passed, freeze self-check passed. New
metric tests cover exact ranking values/cutoff, duplicates, partial alternatives,
source clipping, intent-cluster bootstrap, actual cap removing gold. Report and
handoff prepared locally; NOT committed/pushed in this task. Preserve user's
untracked docs/review2/ plans/diagrams.

## Latest: complete production E5 switch and Huy push, 2026-10-21

User explicitly requested switching entirely from MiniLM, with no parallel legacy
index. Previous production config was sentence-transformers/all-MiniLM-L6-v2;
532 chunks in 5 documents, vector(384). Production now uses
intfloat/multilingual-e5-base, revision d128750597153bb5987e10b1c3493a34e5a4502a,
768 dimensions, normalized vectors, query:/passage: prefixes, 512-token encoder.
The SAME public.document_chunks table was atomically migrated; no sidecar table
was created. All row IDs, document/chunk identities, content, status/timestamps
were verified unchanged. ACL and other non-embedding metadata retained. The 532
cached E5 vectors exactly matched all current live chunk names/texts and were
hash-verified before reuse. No model/corpus downloads or external API calls.

Code updates: pinned E5 profile/default, correct query/passage prefixes,
normalization/dimension checks, pinned tokenizer revision, four-token prefix
reserve for future ingestion. Local ignored .env updated to E5/local/512.
IMPORTANT FOR TEAM: pull Huy and explicitly change EMBEDDING_MODEL in existing
.env to intfloat/multilingual-e5-base, then restart. Old MiniLM query encoders are
incompatible with the now-768-dimensional database. BGE model availability is a
separate requirement; the optional reranker still loads lazily/cached-only unless
RERANKER_ALLOW_DOWNLOAD=1 is explicitly configured on compute host.

Read docs/e5-production-rollout.md and docs/translated-hybrid-rerank.md.
Operational migration script scripts/retrieval/migrate_e5_index.py is dry-run by
default and refuses different content/model. It now must NOT be rerun against the
already migrated index. A restricted recovery-only snapshot is under ignored
.venv/e5-migration-recovery/minilm-index.json; not staged or pushed, not a live
MiniLM fallback. First apply attempt failed its Vector-to-NumPy verification and
fully rolled back; fixed adapter conversion and retry passed every vector check.
Guarded Supabase SQL handles new empty installations/already-E5 databases and
refuses populated MiniLM casts without actual replacement vectors.

Validation: 57 targeted model/retrieval/parser tests passed under E5 config;
4 additional frozen benchmark/replay tests passed; freeze self-check passed with
unchanged manifest c8f9dae06fd70e9e897912aa4a0a7488e98993c88af2b182a1406db72c51f6f3.
Actual offline cached E5 inference produced a normalized 768-dimensional query;
actual authorized dense SQL returned 3 ranked results (~827ms retrieval, startup
excluded). This is a connectivity/model/index smoke, NOT a new quality benchmark
or live Groq/BGE/generation validation. See artifacts/evaluation/
e5-production-rollout-20261021/{preflight,migration,live-smoke}.json.

Reviewed changes committed separately: parser 8e9196f, frozen benchmark 94286f9,
optional translated hybrid+BGE 03385d2, followed by E5 rollout+handoff commit.
Pushing only Huy; main/teammate branches unchanged. Frozen artifacts retain their
original bytes/line endings (so generic whitespace checks on historical CSV/patch
context can warn); code checks pass. Earlier no-commit/no-index-change entries
below describe history and are superseded by this section.

## Latest: optional translated-hybrid + BGE integration, 2026-10-21

User authorized phase 2 after parser adaptation. Added `translated_hybrid_rerank`
to shared contracts, RetrievalService, RAG type annotations, AskRequest, and UI.
Reuses existing translated_hybrid candidate searches (at least 30 fused candidates,
300/branch for the normal top10 request) then original-query/original-chunk BGE
reranking. New src/core/retrieval/reranker.py pins benchmark BGE revision,
FP32/batch4/paircap1024/raw logits/stable ties. Lazy shared model, serialized
inference; CPU/cached-only by default. Explicit RERANKER_ALLOW_DOWNLOAD=1 permits
weights download on compute host; RERANKER_DEVICE=cuda chooses GPU. Tests did not
download or infer model weights, send API questions, or access/write the database.

Read docs/translated-hybrid-rerank.md for before/after, teammate invocation,
configuration and limitations. Source IDs/ACL/company/metadata/document filters
remain intact. Translation failure reranks dense candidates and reports this in
details. Missing reranker weights fail explicitly. Existing hybrid stays default.
No guessed document language: verified mapping available through existing shared
service/RAG parameters; current HTTP UI path has no language-map fields, so it
runs translated search across the authorized corpus and language_aware=false.

IMPORTANT: reuses configured application embedding service/current index; no E5
migration or index compatibility certification. Benchmark E5-base768 result cannot
be claimed for MiniLM384 production index. Existing 5000-character generation
context cap retained. Live end-to-end model/GPU/LLM validation remains for compute
host. No commit/push or history merge performed; working tree also contains phase1
and earlier benchmark files. Keep changes reviewable rather than staging blindly.

Validation: 49 targeted tests passed (command in docs), git diff --check passed.
New tests/test_translated_hybrid_rerank.py covers 7 cases including complete
KnowledgeAgent->RAG->retrieval->rerank->evidence propagation and API acceptance.
Legacy test_app_request_models separately failed import of removed
CandidateReviewRequest; unrelated pre-existing main-refactor test drift. Full
legacy suite not certified. See phase2 validation.json for test command.

## Latest: main parser adapted locally, scope constrained, 2026-10-21

User authorized main parser adaptation first; then expressed concern about
scope and conflicts with teammates. Read parser-main-integration-20261021/
README.md,validation.json,main-relative-fixes.patch. Main re-fetched at7c21626.
Ported main's parser/chunker delta into working tree with explicit paths and
preservation checks after broad src patch was rejected by automatic review.
No Git history merge/commit/push; Huy HEAD279be53. No remote branch touched.
Before publishing, record actual upstream ancestry and separate source sync
from our fixes; current working-tree port is NOT a completed Git merge.

Only3 parser files differ from main: document_processor(top-level table type
normalized),chunking/processor(only skip true heading-only text,never body),
scanned/pdf_ocr(default OCR table metadata when fallback off). Upload and
Upload Test explicitly call parse then chunk; preserved Huy translated_hybrid
support and existing Upload Test embedding_status/error API fields. Two
processing benchmark scripts migrated to canonical imports and chunk stage.
No tokenizer/retrieval implementation,model,DB/vector or evidence change.
682 saved artifact/tokenizer/retrieval files unchanged before this handoff
update; ignored before.patch/backups under .venv/parser-main-integration-20261021.

21 targeted tests pass(8 new parser/upload integration +existing token/source
mapping/evidence tests). Native PDF/Office/CSV checks, optional table contracts
mocked,storage/DB/embedding mocked in upload tests. No model/API/download/live
DB writes. Processing script --help,Python syntax and diff whitespace pass.
Legacy tests still have pre-existing old import paths/obsolete API behavior;
full suite not claimed. No optional OCR-engine model download/run. Existing
PDF flat-text/table duplication not redesigned. Keep next work narrow:
application translated-hybrid + plain BGE reranking integration after user
agrees to continue. All code and previous benchmark work still uncommitted.

## Latest: translated-hybrid result returned and verified, 2026-10-21

User returned Downloads/translated_fresh_results; copied byte-for-byte into
artifacts/evaluation/colab-translated-hybrid-fresh-v1/colab-results,original
retained. Matching exact input ZIP local replay passes48 candidate pairs,
96 rankings/2880 scores,shared-input lineage and independent char coverage.
Read RESULTS.md,findings.json,verification.json/import-manifest.json. Labels
still frozen manifest c8f9dae..., no new inference/API or label changes.

NVIDIA L4 FP32 BGE, same-run dense/plain vs translated-hybrid/plain controls.
Complete per12: dense12/12/12/10 vs hybrid12/12/12/12 for VI→VI,EN→EN,VI→EN,
EN→VI. Overall46/48→48/48,components107/112→112/112. No component/fullcase
regressions. Both control views match original fresh run evidence48/48.
F03 EN→VI Manual5 denseglobal187→hybridcandidate4→rerank2; all3 fields gained.
F08 EN→VI SOP2 denseglobal33→hybridcandidate6→rerank1; both components gained.
All candidate30 availability recovered. Zero truncation(maxpair502/1024).

Important: all24 translations API-valid but F08 translates inventory stock
as 'cổ phiếu'(financial shares). Retrieval succeeds despite semantic error;
do not equate48/48 with translation fidelity or production answer accuracy.
Do not silently fix translations or relabel after seeing outputs. This is
small development followup targeting known misses, not held-out evidence.
Suggested next: independent questions + terminology review, then controlled
integration with main (table-order issue still separate). No integration,
DB/vector change, generation run or deployment. All work still uncommitted.

## Latest: translated-hybrid fresh comparison prepared, 2026-10-21

User authorized next benchmark with frozen questions/evidence; explicitly
approved sending ONLY24 simulated question texts to Groq after automatic
approval review requested consent. Calls completed24/24, zero failures,
existing QueryTranslator auto language detection + Groq openai/gpt-oss-20b.
No documents, labels or credentials were translation inputs. Outputs/usage
saved once; no repeated API calls needed. Production/core code unchanged.

See artifacts/evaluation/colab-translated-hybrid-fresh-v1/README.md,translations.json,
lexical-inputs.json,candidate-inputs.json,translation-summary.json. PostgreSQL
simple lexemes extracted over supplied frozen text in a READ ONLY transaction;
no document table reads/writes. Offline BM25 same production cleanup/formula;
two numeric SQL parity checks passed. Stable chunk-ID tie break substitutes
for unavailable live DB row UUIDs (documented adapter difference).

Uses ACTUAL translated_hybrid.search with frozen repository/translator adapter:
original-query dense, target-language matched original/automatic translated
BM25, RRF60/dense1/BM252. Internal300 per branch(top_k30*10), fused30 for BGE,
final10. All5 target-language docs/admin scope, verified frozen language map.
Original E5 query/document vectors reused, no new E5/model download locally.
Candidate pools frozen before BGE scoring. Same-run NEW dense/plain and
hybrid/plain controls on Colab, shared identical-input score reuse. No
predecessor context, generation or label edits. Review all gains/losses and
F03/F08; this follow-up uses development data, not held-out proof.

New scripts: fresh_translated_candidates.py,prepare_translated_fresh_inputs.py
(--allow-groq only with consent; refuses to replace frozen candidate inputs),
evaluate_translated_fresh_reranker.py,prepare_translated_fresh_colab.py.
Three offline tests pass(BM25/scopes,fallback,full synthetic artifact replay/
wrong-rank rejection). Extracted-final-bundle preflight and ZIP/syntax pass.
Notebook and~3.8MB ZIP ready under colab-translated-hybrid-fresh-v1; copies in
Windows Downloads/translated-hybrid-fresh-v1. User must upload input ZIP to
Colab /content, unzip to translated_fresh_experiment, install bundled extra
requirements, run script --output-dir /content/translated_fresh_results
--allow-download, verify/download returned folder. No key/DB access on Colab.
GPU run is PENDING, no translated-hybrid quality result yet. Compare through
the matching extracted bundle, not later HEAD. All changes uncommitted.

Integrity note: working frozen REVIEW.md contained stray 'run' after 'receipt'.
Preserved edit outside frozen set at fresh-review-assessment-20261021/
REVIEW-before-stray-run-restore.md, restored exact original ZIP bytes. Frozen
manifest still c8f9dae..., questions/evidence scoring labels unchanged.

## Latest: fresh benchmark returned and verified, 2026-10-21

User returned Downloads/fresh_reviewed_results folder. Copied byte-for-byte to
artifacts/evaluation/colab-fresh-reviewed-v1/colab-results; original retained.
Read RESULTS.md and findings.json. Matching uploaded input ZIP extracted to
ignored .venv/colab-review-inputs/<zip_sha>; offline verifier passed48 dense
pools,144 rankings,4320 scores,exact rendering/lineage and independent char
coverage. Preserved original Colab audit as colab-verification.json; added
import-manifest.json. No new GPU/model inference locally.

NVIDIA L4 FP32; complete48 cases, zero truncation(maxpair678/1024,query42/512).
Full evidence per12: dense VI→VI12,EN→EN11,VI→EN8,EN→VI8; ALL THREE rerankers
plain/parent-plain/narrative-parent12,12,12,10, matching candidate30 availability.
Components per28: dense28,26,19,18; rerankers28,28,28,23. All variants have
identical per-case evidence; no regressions vs dense. No extra-context gain
on this fresh set; do not present original post-hoc19/19 as held-out proof.
Remaining EN→VI F03 Manual5 dense187(all3 fields absent frompool), F08 SOP2
rank33(both components absent). Rerankers cannot recover absent candidates.
Suggested followup: cross-language candidate generation/translated-hybrid
comparison under same frozen scope; modest pool expansion may helpF08 but
notF03. No followup experiment run/label edits/production changes. All work
still uncommitted; user has not requested commit/push in this resumed task.

## Latest: fresh Colab benchmark prepared, not yet run, 2026-10-21

User requested running the fresh benchmark and prefers Colab GPU. Prepared
artifacts/evaluation/colab-fresh-reviewed-v1/fresh_reviewed_colab.ipynb and
fresh_reviewed_colab_inputs.zip(~3.5MB). No Colab runtime-control tool exists
in this session; user must upload notebook, select GPU, upload ZIP, run cells,
and return fresh_reviewed_results.zip. Downloads/inference happen on Colab,
not locally. No new model weights downloaded locally or local embedding/
reranker inference. Cached tokenizer-only exhaustive check: query max42/512,
all possible query/passage/variant pairs max682/1024; zero truncation.

New evaluate_fresh_reviewed_reranker.py reuses existing renderer, dense-pool,
scorer and independent character audit. Fresh validator handles new set,
avoids old Q01-Q20 loader. E5 pinned d128750... query: prefix/FP32/cap512;
24 new query embeddings, existing1063 document vectors hash/order-checked;
48 top30 pools frozen with target-language/admin filters, all5 target docs.
BGE953dc6... FP32/cap1024 same runtime: plain,parent-plain,narrative-parent,
final10. Identical inputs reuse ONLY matching scores from this NEW run;
narrative=plain tables,parent narrative. Old-question scores not reused.
Original anchors only earn evidence; no total context budget or generation.
Report dense baseline,candidate30 availability,three reranked variants/all
four directions,components and paired gains/losses. Shared computation times
are NOT independent per-arm latency. Fresh extension is user-approved,
assistant-prepared,not independent held-out proof. Core/production unchanged.

Portable builder: prepare_fresh_reviewed_colab.py. Bundle CRC/code syntax,
extracted-bundle preflight and offline synthetic replay passed; changed
scores and wrong rankings rejected. Test: .venv/bin/python -m unittest
discover -s tests -p test_fresh_reviewed_reranker.py. On return verify with
scripts INSIDE the matching extracted input bundle, not a later Git HEAD.
Notebook ends with verification/download. Failed checkpoints are partial,
not completed benchmarks. Prepared files and previous freeze remain uncommitted.

## Latest: fresh evidence v1 frozen and main reviewed, 2026-10-21

User approved the evidence proposals and authorized freezing; completed
artifacts/evaluation/fresh-reviewed-v1/. 12 bilingual paired intents,24 texts,
48 directional cases,28 required components per direction,72 exact parser
spans. Applied F04 days-of-supply and F09 Manual-specific clarifications;
F02 deck,F05 workbook README,F12 separately extracted SOP table alternatives;
narrowed F06-F08. Converted indexed offsets through saved source_spans into
real parser-source coordinates; existing score_evidence reused unchanged.
Assistant-prepared/reviewed,user-approved in chat,not independently certified
or held-out. Original draft/proposals/sources unchanged. Manifest uses LF
canonical hashes; historical draft CRLF hashes preserved. Script:
scripts/retrieval/freeze_fresh_review_set.py --verify-only --self-check
passes30 original-anchor alternative checks,56 component isolation checks,
24 full/empty oracle pairs and3 tamper checks. Build refuses overwrite.
Do NOT pass new set through old Q01-Q20-hardcoded validator/loader. Fresh
runner adapter/new query vectors/top30 pools/new inference remain next steps;
no retrieval benchmark/model download/DB change occurred. Do not reuse old
question logits. See README and assessment/freeze-verification.json.

User also requested main review after freeze. Fetched main7c21626, two commits
absent from Huy(7e3b483 parsing/chunking split;7c21626 docs). No merge/pull.
See artifacts/archive/main-review-20261021/REVIEW.md and processing-checks.json.
Confirmed DOCX table-order regression: top-level table type ignored during
nested metadata normalization, so table moves to end and short prose merges
across it. Old/new isolated source-archive fixture verified. CSV control passes.
Markdown first-fact deletion reproduces on both old/new: pre-existing issue.
Frozen benchmarks unaffected; fix order contract before new parsing snapshots.
No production fixes applied. Freeze/review changes remain uncommitted.

## New task: fresh question review packet prepared

User authorized preparing fresh questions and comparison. See
`artifacts/evaluation/fresh-review-20261020/README.md` and REVIEW.md:24 question
texts,12 paired bilingual intents,48 directional cases; exact chunk-content
excerpts/offsets and a human review CSV. Assistant draft, not independently
held-out. Some overlap with older broad intents; equivalents and novelty need
review. Three structured-table intents, one mixed PDF, eight narrative; no
workbook-specific table question yet. Existing benchmark untouched. No new
inference/download. Saved old-question scores cannot evaluate new questions.
Review/approve labels first, then adapt the Colab runner/evidence adapter and
freeze E5 top30 pools for plain/parent-plain/narrative-parent comparison.
Draft labels use indexed-chunk offsets, not evidence-v3 parser offsets.

## Latest completed result: Q20 recovery with narrative-only context

User requested solving Q20. Completed a general metadata policy: structured
table candidates use plain original text; only non-table candidates receive the
existing conservative preceding-source context. No question IDs, filename
exceptions, label edits or score adjustments. Exact inputs already had saved
plain/parent Colab scores, so this was verified offline without new inference,
model download, API usage or GPU. Read
`artifacts/evaluation/reranker-narrative-context-20261020/RESULTS.md`.

VI->VI improves18/19 to19/19 eligible intents and60/61 to61/61 components.
Q20 proposal_checks recovered; Q13 and Q15 gains retained. Other directions
stay15/19,12/19,12/19; no required-component regressions across80 cases against
the prior parent-plain variant. Q14 remains excluded from full success.
Verified160 rankings/4800 saved entries, exact rendering/score lineage and
independent character coverage. See verification.json, score-lineage.json and
changes-vs-parent.json. Script: scripts/retrieval/evaluate_narrative_context.py;
shared runner mode: narrative-parent. This supersedes Q20-pending notes below.
Post-hoc diagnostic on a repeatedly inspected small set, not held-out proof or
answer accuracy. Production integration remains pending. No commit/push done.

## School resume checkpoint: evidence v3 task complete, 2026-10-20

### Newest result: Colab metadata-context ablation completed

**Newest COMPLETED experiment:** plain vs plain+predecessor without metadata
prefixes. User returned `reranker_parent_plain_results.zip`; reviewed and
verified locally. Read `artifacts/evaluation/colab-reranker-parent-plain-20261020/RESULTS.md`
and `findings.json`. All160 rankings/4800 score entries passed, same v3 labels,
same E5 top30, pinned BGE reranker, both arms FP32 on Colab T4. VI→VI17→18/19,
EN→EN14→15, VI→EN12→12, EN→VI12→12; components59→60/61,55→56,46→47,49→49.
Q01VI stays complete. Q13guard21→5 gives9/9; Q15guard27→1 gives4/4. Q20 still
regresses: workbook KPI summary13→6 pushes manual pre-PO checklist10→11.
Only Q20VI remains incomplete in that direction (Q14 excluded). New plain
control matches all80 previous plain FP32 orders/evidence exactly. No label
changes or production rollout. Keep this variant promising but experimental;
next possible work is Q20 final-selection/context-to-source-unit behavior and
fresh human-reviewed/held-out cases, not automatic new model comparisons.
All changes/results remain local/uncommitted unless a later commit records them.
No local model download resumed. This completion supersedes the pending note
immediately below.

**Newest pending experiment:** user authorized plain-vs-predecessor without
metadata prefixes and inspection of the next results. Prepared
`artifacts/evaluation/colab-reranker-parent-plain-20261020/` (PLAN, preflight,
notebook and22MB bundle). GPU execution requires the user to run Colab; no new
results exist yet. Runner `--context-mode parent-plain` controls plain original
text vs same13 predecessor mappings,69 changed pairs, max686tokens, v3 labels
unchanged. No local model download/inference. Return ZIP:
`reranker_parent_plain_results.zip`. Then run
`analyze_results.py --parent-plain` from the original context-review folder;
it verifies against the matching uploaded bundle rather than assuming current
Git HEAD equals the experiment's source commit. Inspect Q01/Q13/Q15/Q20 and
all directions. No new label changes or production configuration authorized.

**Newer completed result:** user returned the predecessor experiment ZIP. Read
`artifacts/evaluation/colab-reranker-parent-20261020/RESULTS.md` and `findings.json`.
Local verification passed160 rankings/4800 saved entries; same v3 labels and
E5 pools, paired metadata-only vs metadata+preceding-source-text on Colab T4
float32. Guard Q13VI→VI21→5,8/9→9/9; Q15VI→VI21→1,3/4→4/4. Q20VI→VI regresses:
workbook summary13→6 pushes manual proposal-checks10→11. Counts metadata→parent:
VI→VI16→17/19, EN→EN14→15, VI→EN12→12 (partial Q13.freeze gained), EN→VI12→12.
Components58→59/61,55→56,46→47,49→49 respectively. Earlier metadata-control
orders/evidence match all80 cases exactly. Against ORIGINAL PLAIN reranker,
VI→VI is still17/19: new failuresQ01/Q20 replace oldQ13/Q15. Do not claim an
overall VI gain over plain or globally deploy. Source-body context helped the
targeted short clauses; parent-without-metadata vs plain is a possible future
ablation, not implemented. All experiment/review changes remain local and
uncommitted unless a later commit records them. No local model download resumed.

Follow-up requested: user said "start experiment" for actual preceding source
text. Prepared `artifacts/evaluation/colab-reranker-parent-20261020/` with
`PLAN.md`, new notebook,22MB input bundle and local tokenizer preflight. User
must start Colab GPU execution; no remote notebook/session control is available
from this laptop and no inference result exists yet. Compare **metadata-only
control vs metadata + preceding source passage**, both on the same GPU, using
`--context-mode parent`. Default metadata experiment stays backward compatible.
Parent mode's legacy `plain_*` JSON keys mean metadata-only control; config
explicitly records `control_mode=metadata`. Same candidates/v3 labels/top10.
Conservative same-location/ACL/nonconflicting-section rule changes13 passages
and69/2400 pairs; max718 tokens, no overlength. Additional source text is ranking-
only and cannot earn coverage. No local model download or API calls. New files
are uncommitted. Expected return ZIP: `reranker_parent_context_results.zip`.

Read `artifacts/evaluation/colab-reranker-context-20261020/RESULTS.md` and
`findings.json`. The user ran the prepared notebook and returned
`reranker_context_results.zip`; the laptop verified the artifacts without
loading a model. All 160 paired rankings/4,800 saved score entries and character
coverage replayed. Same BGE revision, E5 top30, v3 labels, both arms float32
on Colab A100, no total context-token cap. Short-input metadata prefixes
(<=800 characters) yielded VI→VI **17→16/19**, components59→58/61; other
directions unchanged (EN→EN14/19, VI→EN12/19, EN→VI12/19). No required-component
gains; Q01.approval is the sole loss, training-deck cover rank10→14.
Q13 guard21→21, still8/9; Q15 guard27→21, still3/4. Form table11→6 does not
add coverage because the transaction-ID alternative was already recognized.
Do not promote the prefix rule. A source-body/parent-context experiment remains
unimplemented; metadata context alone did not fix the omissions.

New runner `scripts/retrieval/evaluate_reranker_source_context.py`, notebook,
portable22MB input bundle, results and analysis are local/uncommitted unless a
later commit records them. Original returned ZIP is preserved. Local model
download was paused/cancelled; never resume it implicitly. HF Inference API
probe returned402 (no credits); no benchmark text was sent there. Colab ran
the model remotely instead. No API key is needed for the notebook. Never
commit `.env` or ignored `.venv` download/cache files. No production, database,
label change or new embedding-model comparison was performed.

The session stopped for allowance yesterday; user resumed and authorized finishing, pushing Huy and leaving this handoff. Existing work through code/v3 rescore was already committed as cca4226 (add VietStyle English evidence benchmark); this follow-up finishes documentation/verification. Read evidence-v3/README.md and dense-evidence-benchmark-v1/rescored-evidence-v3/comparison.md first.

Implemented one new VI alternative for Q15.transaction_id: same explicit post-approval transaction-ID field in SOP parser5, chars[888,947), which the reranker already had at rank4. EN equivalent already labelled, unchanged. v3 hash cf022622eafcde551eac6ba26e3bd4f8aac7fc4239533dd951e5dbac1cb648e3; parent v2 hash6e7a502a4b99cd347940f8c28562ed19d082c2761e8f2e0bbf75f75d142a7f0b. All old spans, all other requirements, sources/questions/reference answers and Q15.history unchanged. Q14 still unresolved.66 components/61 required ready,199 spans(100VI/99EN),19 fully-ready intents. rescore script adds --previous-evidence, --previous-results-dir and optional --reranker-report, with saved-vector/logit/hash replay and independent character check.320 case rankings rescored;21 targeted tests passed on resume (17 evidence +4 reranker); no model/GPU/DB/API rerun. Q15 reranker2→3/4 but still incomplete because no-delete/direct-source-edit guard remains missing. VI->VI totals under v3: E5dense17/19, BGE-M3dense15/19, Qwen14/19, E5+BGE reranker17/19. Source/rankings unchanged: score changes reflect annotation only. v1/v2 artifacts preserved.

Next authorized evidence-fix task is DONE; do not repeat downloads or GPU benchmarks. Suggested next experiment (not yet implemented): source/section context for short reranker passages, especially the missing history guard (Q15 rank27; Q13 rank21). Fixing the duplicate label does not itself improve retrieval. Keep reranker experimental; no production integration, re-embedding or database changes. User explicitly removed all total context-token caps; previous budgeted neighbor experiments are historical only. No new model comparison unless requested. Historical runners retain v2 for reproducibility; evaluate their saved outputs against v3 through documented rescore options. Use English by default; Vietnamese on request. Explain code before/after and checks.

## Latest: Q15 regression analyzed, 2026-10-19

Read reranker-bge-v2-m3-v1/Q15_ANALYSIS.md. Corrects earlier overstatement: official v2 4/4→2/4, but transaction ID remains explicitly in reranker rank4, SOP parser5 Unicode[888,947) (“Adjustment Transaction ID Mã giao dịch điều chỉnh sau duyệt”). Label only accepts separately extracted table SOP8, dense9→rerank11. This is a confirmed missing equivalent-source alternative. History guard SOP4 dense7→rerank27 is a genuine omission of the explicit no-delete/no-direct-source-edit detail; registry rank9 has related no-overwrite-history wording but is not automatically sufficient for both prohibitions. Core fields and timestamp/counter retained ranks1/4. Promoted SOP cover/AI/general-policy chunks occupy slots; relevance sorting does not enforce complete multi-fact coverage. Table lacks section_title and inherited form caption; context-deficit cause is plausible, not experimentally proven. No label/vector/rank/score changes or GPU rerun. Even accepting the transaction-ID alternative would leave Q15 full-intent failed due to history. Next consider bilingual/source-wide review of duplicate label and controlled context-prefix/parent experiment before swapping models. All work uncommitted.

## Latest: no-budget cross-encoder reranker benchmark completed, 2026-10-19

User clarified token question concerned chatting with Codex and explicitly removed context-token caps from future work. User authorized us to implement reranker assuming An lacks one. Read dense-evidence-benchmark-v1/reranker-bge-v2-m3-v1/{comparison,IMPLEMENTATION}.md. Existing Huy evaluate_rerankers.py used CrossEncoder for older Vinamilk evaluation; not production, not found in cached QuocAn fdfe6ca (latest remote fetch blocked by authentication). Explained CrossEncoder is the library/model architecture and BGE-reranker-v2-m3 is the trained model, separate from E5 embedding. New evaluate_vietstyle_reranker.py +4 tests reuse old model registry/scorer and saved E5 vectors. Downloaded runtime weights to WSL HF cache, pinned953dc6f6f85a1b2dbfca4c34a2796e7dde08d41e, then ran offline RTX2060 fp16 batch2. E5top30→BGEraw-logit-sort→top10; both outputs10 chunks, no context budget; per-pair max507 under configured1024, zero truncation.80 cases/2400 scores independently replayed (--verify-only),4 new tests passed. VI->VI full17→17/19, EN->EN14→14, VI->EN9→12, EN->VI12→12. Candidate-pool full availability19/18/14/14 respectively; not top10 oracle. VI fixesQ20(M13dense12→rerank7), losesQ15(transaction form11, no-delete guard27). Q13improves6→8/9 components but guard remainsrank21. Q01regresses in3 directions. Mean added rerank402ms, median379ms, excludes loading/dense/generation; peakGPU1114MiB. Do not enable globally based on current Vietnamese result; inspect short guard/field evidence selection and seek held-out evaluation next. No production, DB/index, embedding_service, translation or LLM changes. Original artifacts unchanged; all work uncommitted. User prefers English, switches Vietnamese on request. Continue explaining before/after code changes so user can follow.

## Latest: fixed-budget E5 neighbor test completed, 2026-10-19

User authorized neighbor test and asked whether Vietnamese uses more tokens. Added evaluate_neighbor_context.py +4 tests, no production changes. Read dense-evidence-benchmark-v1/neighbor-context-e5-v1/{comparison,IMPLEMENTATION}.md. Predeclared2048/4096 caps, exact rendered context counted by pinned E5 tokenizer (proxy, not LLM/chat tokenizer). Policies: dense10, interleaved seed→previous→next within same doc/lang/ACL, dense30; whole chunks only, dedup and skip overbudget, no gold-guided selection. 80 saved rankings replayed,560 context variants scored; baseline equals v2; independent character coverage and560 selection audits passed;19 targeted tests passed. VI->VI complete cases/19: at2048 dense10=16,neighbors13,dense30=16; at4096 dense10=17,neighbors17,dense30=18. Neighbors fixesQ13 but at4096 losesQ11 (budget crowding); at2048 gainsQ13 but losesQ07/Q12/Q16/Q17. Q20 not fixed by neighbors; dense30_4096 fixesQ20 but still missesQ13. Mean context tokens at4096: dense10 2417,neighbors4022,dense30 4043. Do not promote blanket expansion; recommend next reranker experiment on broad candidates with fixed budget, or explicit selective expansion as a new ablation. Small post-hoc set, not held-out. Same20 paired raw queries: E5/BGE549VI vs553EN(0.99x);Qwen578VI vs500EN(1.156x). No universal Vietnamese multiplier, not a chat billing estimate. No GPU/encoder/generation/DB/translation changes. Old artifacts unchanged; all work remains uncommitted.

## Latest: evidence v2 review and all-model rescore completed, 2026-10-19

User authorized us to review labels and rescore. Read evidence-v2/README.md and annotation-changes.json. Read 20 definitions; source-focused bilingual audit Q11/Q12/Q13/Q18/Q20, not exhaustive independent corpus relabelling. Added complete alternatives Q11 conflict/checks, Q12 verify, Q20 no-write/citation/conflict; Q18.no_guess now optional but missing actual PO/backorder evidence still required. Q20 normal Planner→Procurement flow required; exceptional branch optional. Q13 and Q14 objects unchanged; Q14 still unresolved. 66 components:61 required ready,2 unresolved,3optional;198 spans (99/language). Validator now accepts --folder; defaults v1. New rescore_vietstyle_evidence.py verifies old hashes, replays dense top10 and independently checks new character coverage. No GPU/model/vector/rank change; original v1 untouched. 15 evidence tests passed and 240 rankings rescored. New results under dense-evidence-benchmark-v1/rescored-evidence-v2/. Full evidence counts per19 v1→v2: VI->VI E5 15→17, BGE13→14, Qwen13→14; EN->EN13→14/14→15/13→14; VI->EN8→9/14→15/14→15; EN->VI11→12/13→14/12→13. E5 VI->VI remains incomplete Q13 and Q20. This is post-hoc label correction, not model improvement or independent held-out evidence. Component denominator now61 vs62. No production/DB/translation changes, no generation evaluation. Next: discuss/measure real retrieval gaps Q13/Q20 with fixed labels and explicit context budget, or obtain human policy-role resolution. All changes still uncommitted.

## Latest: reviewed E5 VI->VI losses, 2026-10-19

Read dense-evidence-benchmark-v1/LOSS_ANALYSIS_VI.md. User requested analysis, no label or retrieval edits. Q11 2/3: existing sole AND alternative requires CSV index2 at rank17, but SOP index3 rank3 + Deck index3 rank9 provide strong equivalent checklist candidate. Q13 6/9: genuine missing preparation/blind-count details in SOP index1 rank17; no-delete-source guard SOP index4 rank27, though audit-trail summary exists rank3. Q18 1/2: workbook rank1 explicitly missing PO/backorder and zero placeholders; failure requires extra no-guess slide rank15, a potentially excessive retrieval criterion. Q20 3/5: true missing approval chain Manual index13 rank12; conflict alternative SOP rank9 + CSV rank10 not accepted because label only Manual index14 rank27. Strict minimal k values17/27/15/27 are diagnostics from saved vectors, not recommended tuning. Current 15/19 scores unchanged. No confirmed generation behavior; no encoder truncation. Next: review evidence v2 consistently for all models/languages before context expansion/reranking experiments. No automatic label changes or GPU rerun.

## Step 3 dense evidence benchmark completed, 2026-10-19

Latest completed task: wired optional evidence scoring into existing evaluate_embedding_candidates.py, added prepare_vietstyle_evidence_benchmark.py and independent saved-vector replay/compare_vietstyle_evidence.py. Read artifacts/evaluation/vietstyle-bilingual-20261019/dense-evidence-benchmark-v1/{IMPLEMENTATION,comparison,INSIGHTS}.md. Shared 1,063 unchanged parser passages with source mapping (532 VI + 531 EN); all three pinned cached tokenizers passed cap512 including formatting (E5 max476, BGE474, Qwen425), zero truncation. 80 cases/model reuse 20 paired intents across four directions, each searching all 5 target-language documents; no gold-source filtering. Language field exists only in experimental snapshot, no database change. Ran E5-base/BGE-M3/Qwen0.6B on RTX2060, float32, batches2/2/1, entirely offline cached weights. Independent replay verified all 240 rankings and character/component coverage; 11 evidence tests plus 4 mapping tests passed. Full evidence success (19 eligible intents, Q14 excluded): VI->VI E5 15, BGE13, Qwen13; EN->EN 13/14/13; VI->EN 8/14/14; EN->VI 11/13/12. Ready component totals62 per direction include clear parts of Q14. E5 VI->VI covers55/62, BGE53/62, Qwen51/62. Source-file diagnostics retained but not comparable to new evidence metrics. No MiniLM run under the new metric, no translation/hybrid/reranker/generation, no production/index change. Next suggestion: inspect E5 VI->VI missing cases Q11,Q13,Q18,Q20 and confirm alternative-evidence labels before changing retrieval or committing to a model. Results are label-dependent and small-sample, not answer-generation accuracy. All changes remain uncommitted, including earlier stages. No push authorized for this task.

## Step 2 evidence scorer implemented, 2026-10-19

Latest: `src/core/evaluation/evidence_metrics.py::score_evidence` now scores frozen top-k chunk provenance against required ready components: union exact source intervals, AND within alternative bundles, OR across bundles. Ignore whitespace gaps only. Duplicate ranking slots remain consumed; overlap does not inflate coverage. Missing/stale/tampered mappings raise rather than becoming misses. Q14 full success stays null; optional/pending excluded from ready denominator. Inputs are dict chunks with text/metadata and target-language source lookup; run existing label validator before scoring. Read evidence-v1/evidence-coverage-step2.md and JSON. Seven new tests plus eight related tests passed. Oracle integration with all source chunks (not model retrieval) covers 62 required ready components and 19 eligible intents in both languages; empty rankings cover zero. No production ranking/model/DB/GPU change. Next: wire this into the offline dense candidate benchmark, preserving provenance alongside vectors. Context expansion still separate. All current work remains uncommitted; do not overwrite earlier uncommitted work.

## Step 1 source mapping implemented, 2026-10-19

The user asked to proceed in explained parts. Part 1 adds automatic source provenance at the existing shared tokenization boundary. Read evidence-v1/source-mapping-step1.md and its JSON audit. TokenCounter now has split_text_with_offsets while split_text preserves its prior string-only API. build_embedding_chunks adds source_parser_index, source_content_sha256, source_child_index/count, and exact source_spans (source and output Unicode ranges). Repeated headers map separately from later body rows; CRLF normalization is mapped without falsely claiming omitted source text. No substring-guess mapping. Existing text/metadata/index behavior was verified against legacy code on 1,063 source passages using cached MiniLM/Qwen tokenizers at caps 512 and 384; no non-whitespace source text lost, all spans exact. Eight targeted tests passed. No encoder weights/model/GPU/DB/API execution or database/index migration. Source mapping is in metadata for future newly built chunks only. It does not cause dense to retrieve A+B and does not fix row-aware splitting. Next part: evaluation-only evidence interval coverage/scorer, then local benchmark wiring; context expansion must be evaluated separately. Existing saved snapshots remain unchanged. Current changes are uncommitted.

## Evidence labels v1 created, 2026-10-19

The user authorized creating evaluation-only evidence labels, not a GPU benchmark or retrieval changes. Read `artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1/README.md` and REVIEW.md. The 20 existing VN/EN question pairs now have 65 answer components and 184 exact source spans (92 per language), with alternative bundles, hashes, Unicode offsets and source metadata. There are 62 ready required components, 2 pending approval-role components in Q14, and 1 optional context component. Nineteen intents are fully ready; Q14 must be reported separately until Manual/SOP role variations are clarified. Calculation inputs in Q09/Q10 come from questions; formulas/defaults come from sources. Q18 is unavailable-data abstention, not a real zero-valued PO lookup. No old source/question/reference/result files were changed. The standard-library validator `scripts/retrieval/validate_vietstyle_evidence.py --self-check` passed exact-quote/hash/location/bilingual/derivation checks and rejects tampered quotes/wrong-language sources. No retrieval-to-evidence mapping/scorer is implemented yet; create/validate it before a new benchmark, preserving source provenance across final chunk splitting. Never index labels or reference answers, or use them to guide ranking. Labels are assistant-curated, not independently human-certified; alternatives remain non-exhaustive. No live DB/model changes, inference API, model loading or GPU rerun.

## Corrected English simulation pack created locally, 2026-10-19

The user authorized us to create the English counterpart ourselves. `artifacts/evaluation/vietstyle-bilingual-20261019/corrected-en-v1/` now contains all five corrected English files; the original mixed-language download remains under sources/en/. Read BUILD_NOTES.md and english-build-manifest.json. The DOCX is unchanged; CSV SLA/workbook/slide text is translated; the SOP is rebuilt from the frozen VN content as a clean selectable-text three-page PDF with all 8 sections and 3 complete tables. Workbook coordinates/types/values/formulas and CSV policy IDs/non-SLA fields are verified unchanged. Twenty English questions/reference answers are in benchmark-questions-en-v1.json, with inherited source-file labels and the missing README limitation retained. These are assistant translations, not independent human-certified gold or new answer-bearing passage labels. Build script: scripts/retrieval/build_vietstyle_english.py (stdlib + existing PyMuPDF). Corrected files were reparsed locally; ZIP CRC/contents and hashes were checked; PDF pages visually inspected. No production code, live model or DB changes, and no model/benchmark run yet. Next is a versioned local benchmark with clearly defined language scope and evidence labels; do not index question/reference-answer files as retrieval evidence.

## English pack received: local quality audit, 2026-10-19

The downloaded `VietStyle_Inventory_Documents_English.zip` has been extracted locally under `artifacts/evaluation/vietstyle-bilingual-20261019/sources/en/`. Read that folder's `READINESS.md` before attempting a new benchmark. The pack is incomplete English: the SOP PDF body remains substantially Vietnamese with broken glyphs visible in the PDF itself; CSV SLA cells, workbook cells and slides 2/8 also retain Vietnamese. Five files parsed to 530 chunks, hashes/counts verified. No embedding/model/GPU/DB/inference API execution was performed. The archive lacks English questions/answers and README. A 20-question assistant-translated draft is saved for human review, not yet scored. An exploratory as-is run was offered as an option; absent explicit preference the recommendation is to correct the English pack first. No production code or historical results were changed. This audit does not supersede the laptop's label/chunking findings below.

## Latest update: laptop review completed

The laptop completed agreed steps 1–4 against Huy `2aa9187`: fast-forwarded
the checkout, independently replayed saved vectors, inspected representative
failures, and reviewed production chunking. Read
`artifacts/evaluation/laptop-review-20261019/REPORT.md` first, alongside the
two earlier comparison reports below. This section supersedes the instructions
below to start the laptop review; the earlier experiment descriptions remain
historical context.

- All **244 saved top-ten orders** and case metrics reproduced: 100 VietStyle
  orders (including MiniLM) and 144 financial four-direction orders. Seventeen
  file hash checks passed, six after explicitly recorded CRLF-to-LF text
  normalization on Windows. Vector-file hashes matched byte-for-byte.
- Original PDFs and cached pages were checked. Every extracted page word is
  covered by the final 525 financial chunks. Encoder execution and tokenizer
  audits were not rerun; replay uses saved vectors, not new embeddings.
- Confirmed score inflation: Q18-en and Q19-en receive full page recall for
  BGE and Qwen by retrieving only Long Hau page-8 header chunk 48, without
  the requested figures. Revenue is in chunk 49; profit before tax in chunk 51.
- Confirmed label limitation: Q14-en ranks the cover naming Ernst & Young
  first for all models, but the label only accepts audit-report page 5.
- Q01-en/Q03-en/Q06-en contain relevant text in the corpus but their first
  labeled-page hits are below ten for every model. See `gold-page-ranks.md`
  for all 48 queries; page hits still do not prove passage correctness.
- Production parser-level table chunks preserve rows and repeat headers.
  The final token splitter can cut overlong rows/sentences and does not add
  explicit original parser-chunk identity/child-part metadata. These are
  code-path risks, not demonstrated causes of every saved failure.
- Windows Git autocrlf changes frozen text checkout hashes. The current
  candidate runner requires exact raw hashes; address LF preservation before
  future Windows reruns. The review records normalization explicitly and
  does not modify historical inputs or weaken the candidate runner.

Only review artifacts were added; no application code, live model, database,
original benchmark results, or source labels were changed. No models were
downloaded/loaded, and no GPU, inference API or database access was used.
The full regression suite was not rerun; do not claim it is green.

### Next session at home

1. Pull `Huy`, check the worktree, and read the laptop review. Do not replay
   completed GPU benchmarks merely because the GPU is available.
2. The English VietStyle set had **not arrived** at the end of this session.
   If it is now available, verify fact/number/table/question/evidence alignment
   and freeze a new version before testing. Otherwise continue label and
   chunking planning using saved evidence.
3. Before implementing changes, explain file/function, old/new behavior,
   reason and verification plan to the user. Proposed order: parser-to-child
   traceability; sentence/row-aware final token fitting; a shared model input
   recipe when a model is selected; answer-bearing and alternative labels.
   These proposals are not yet implemented or benchmarked.
4. Keep dense encoder experiments separate from translated-hybrid pipeline
   tests. Do not convert the experimental 60-word rule into production policy.
5. No final model has been chosen, and no live vector migration is requested.

Offline replay (NumPy + standard library only):

```bash
.venv/bin/python artifacts/evaluation/laptop-review-20261019/review_saved.py
```

On Windows use `.venv/Scripts/python.exe -X utf8` instead. This regenerates
`verification.json` and `gold-page-ranks.md` in the review folder; it does not
load models, connect to services, or alter the original experiment folders.

## Where we are

- Project: enterprise-knowledge-ai-agent. Working branch: `Huy`.
- Last implementation/benchmark commit before this note: `fa651ccae7ca15ddcd654e9280846f750da8647d` (benchmark multilingual embeddings in four situations using old dataset). At handoff creation, local Huy and local origin/Huy both pointed to this commit and the worktree was clean.
- Main was previously merged into Huy in `f7d49e6`, based on main `298be61`. Do not assume these are still the latest remote commits; inspect before merging anything.
- Desktop project path: `/home/eroz/projects/enterprise-knowledge-ai-agent` inside Ubuntu WSL. WSL disk is `F:\WSL\Ubuntu\ext4.vhdx`. These paths are desktop-specific; locate the laptop checkout rather than assuming the same path.
- The user now owns tokenization and embedding-model comparison, in addition to retrieval. Current objective: choose a model and chunking strategy that work for Vietnamese and English queries/documents, including cross-language retrieval.
- No final embedding model has been selected. Candidate benchmarking has NOT replaced the live application's index/model.

## User preferences and agreed next step

Explain in straightforward Vietnamese or English. The user explicitly asks that every code change be explained: file/function, what the old code did, what the new code does, why, and how it was verified. Do not make unexplained changes.

The user is asking a teammate to make an English version of the existing VietStyle simulated document set. It should preserve the facts, numbers, tables, rules and content structure, with corresponding translations of the 20 questions and answer/evidence labels. A newly invented unrelated English scenario would not isolate the language effect.

While waiting, we completed a four-direction pilot using two older financial reports. Next: review the results and chunking limitations, then evaluate the new bilingual VietStyle set when it arrives. Do not keep downloading/running new models without a reason. No deployment or database replacement is currently requested.

## Read these reports first

1. `artifacts/evaluation/embedding-comparison-20261018/comparison.md` — VietStyle model comparison, code changes, metrics and limitations.
2. `artifacts/evaluation/four-direction-20261018/comparison.md` — completed four-direction dense pilot, per-case scores and limitations.
3. `artifacts/evaluation/embedding-comparison-20261018/database-restoration.md` — why/how the cleaned database was made benchmark-ready.
4. `artifacts/evaluation/embedding-comparison-20261018/four-direction-readiness.md` — historical preparation plan only; the actual four-direction test is now complete. Its original reconstruction/metric questions are resolved in report 2.

The corpora, vectors, configs and JSON results in both benchmark directories are tracked in Git, including `.npy` files. Logs matching `*.log` are ignored and may exist only on the desktop. Model weights and `.env` credentials are NOT in Git.

## Experiment A: VietStyle, 20 Vietnamese questions

Frozen folder: `artifacts/evaluation/embedding-comparison-20261018/`.

- Five documents, 532 unchanged indexed chunks; 20 VN questions from An's benchmark.
- Document types/counts: policy manual DOCX 18; SOP PDF 9; registry CSV 12; inventory planner XLSX 485; training PPTX 8.
- Inspected text samples are mainly Vietnamese with English terms. No separate verified English document set in this benchmark. All 532 frozen chunk metadata language attributes were missing when audited.
- Metric is expected-source FILE coverage in top 10 chunks, NOT exact relevant chunk recall or answer accuracy.
- README.txt is absent but remains required by labels for Q01/Q18/Q19; maximum mean source coverage with available files is 95%, not 100%.

| Model | Source-file recall@10 | Full expected-source cases |
| --- | ---: | ---: |
| sentence-transformers/all-MiniLM-L6-v2 baseline | 80.00% | 10/20 |
| intfloat/multilingual-e5-base | 93.33% | 16/20 |
| BAAI/bge-m3, dense embeddings only | 89.17% | 15/20 |
| Qwen/Qwen3-Embedding-0.6B | 86.67% | 13/20 |
| intfloat/e5-large-v2 | 78.33% | 10/20 |

E5-large-v2 is English-only per its model card; multilingual-e5-base is a DIFFERENT model. BGE-M3 and Qwen3-Embedding are multilingual too. More parameters did not guarantee a better score here. These small, source-file-labelled results did not establish cross-language quality.

All candidates ran locally on RTX 2060 in float32, cap 512; E5/BGE batch 2, Qwen batch 1. No inference API received document text. Model downloads are local Hugging Face caches. Local cosine replay reproduced all 20 original MiniLM database top-ten orders. All 80 candidate case scores/rankings (4 models x 20) were independently verified from saved vectors.

Frozen corpus SHA256: `a52fdb6efaadfe428f7c477617b4c0b8072a30d3e3b9596dbfa205b67cc01352`.

## Experiment B: completed four-direction pilot

Frozen folder: `artifacts/evaluation/four-direction-20261018/`.

- Full original PDFs: PVFCCo English annual report (96 pages) and Long Hau Vietnamese financial statements (22 pages).
- `data/raw/benchmark_data/2.BCTC da kiem toan 2008 (V).pdf` and the misleadingly named `HPT - To trinh thong qua danh sach Cong ty Kiem toan signed1.pdf` have IDENTICAL bytes/SHA256; both are the same Long Hau source.
- There was no complete retained 249-chunk old index. Partial historical retrieved contexts were recovered from local origin/QuocAn benchmark artifacts and saved in `retained-original-contexts.json`; these are used ONLY to validate old evidence, not as a ranking corpus.
- Rebuilt from complete PDFs locally: native PDF text where available; missing text OCR with Tesseract eng/vie, 200 DPI, PSM 3. Installed Tesseract in desktop WSL; not a Python dependency or an application code change. OCR noise and flattened tables remain.
- Final corpus: 118 pages, 525 common chunks (348 EN / 177 VI), 60 whitespace words per chunk with 12-word overlap, page boundaries preserved. Two English pages (2, 95) yield no text; none of the gold pages is empty. Every extracted page word is covered.
- 24 paired intents / 48 queries, NOT 48 independent intents. Source question files are `data/evaluation/long_hau_2008_cases.json` and `_en.json`; IDs and evidence labels align.
- 12 English-document-only intents yield 12 VI->EN and 12 EN->EN cases; 10 Vietnamese-document-only intents yield 10 VI->VI and 10 EN->VI. Two mixed-document intents produce four queries and are scored separately.
- Every query ranks chunks from BOTH complete reports. Target language and gold labels DO NOT restrict retrieval. No translation, BM25, reranker, generation, inference API or Supabase writes.
- Metric: fraction of labelled EVIDENCE PAGES appearing among top 10 chunks, with duplicate page hits counted once. Also MRR@10 over page hits. Original chunk indices are not reused after rechunking. Getting another chunk from the same page counts here even if that particular chunk does not contain the answer: this is a coarse metric, not answer correctness.

| Query -> evidence document | Queries | E5-base multilingual | BGE-M3 | Qwen3-0.6B |
| --- | ---: | ---: | ---: | ---: |
| VI -> VI | 10 | 80.00% | 80.00% | 70.00% |
| EN -> EN | 12 | 41.67% | 41.67% | 41.67% |
| VI -> EN | 12 | 66.67% | 41.67% | 50.00% |
| EN -> VI | 10 | 10.00% | 80.00% | 70.00% |
| Four-direction macro, equal direction weights | 44 | 49.58% | 60.83% | 57.92% |

All 144 final top-ten orders and page metrics were independently recomputed from saved passage/query vectors. Four focused candidate-runner unit checks passed. All final inputs fit 512 tokens, including required prefixes: max passage E5 234, BGE 232, Qwen 465. No silent truncation.

IMPORTANT: `preflight-100-word-attempt/` contains a SUPERSEDED, incomplete attempt. Initially 100-word chunks / 20 overlap yielded 333 chunks; Qwen rejected 11 inputs over the configured cap 512. We preserved that attempt, reduced the common chunk size, checked all three tokenizers before embedding, and reran ALL THREE models. Use only the top-level FINAL `candidates/` for the result table above. The 512 cap was an experimental setting, not Qwen's native maximum.

Limitations: English and Vietnamese reports have different topics, lengths and extraction quality; direction groups are only 10/12 cases. Chunk size and incomplete alternative-evidence labels affect scores. These are pilot findings, not proof of universal model superiority. Do not compare these percentages directly with Experiment A (file labels) or the original 249-chunk financial benchmark (chunk labels). E5's strong VietStyle score did NOT translate into winning every direction; BGE was stronger EN->VI in this pilot.

Frozen corpus SHA256: `b8e46d0776b602ace3d74efbc7cb14cfa554377294219a1f1615f7fa15f890e4`.

## Relevant code and what changed

- `scripts/retrieval/evaluate_embedding_candidates.py`: separate local benchmark runner. Model option/config, pinned revision/tokenizer, required prefixes/instructions, input token audit, normalized vectors, cosine top 10, scoped/role-visible frozen corpus. Creates per-model config, passage/query vectors, results; refuses to overwrite completed outputs. Extended with OPTIONAL gold-page scoring/grouping; prior VietStyle file scoring retained.
- `scripts/retrieval/prepare_four_direction_benchmark.py`: reconstructs complete PDFs, cached page text/OCR, common chunks, bilingual cases, page-label validation, hashes, and preflight for all three tokenizers before spending GPU time. Requires retained-original-contexts.json included in the snapshot. Cached pages avoid redoing OCR. Re-running preparation is unnecessary just to analyze saved results.
- `scripts/retrieval/evaluate_vietstyle_dense.py`: read-only live-Supabase baseline, verifies exact frozen corpus/vectors and encoder config before measuring. Requires DB credentials; not needed for offline candidate analysis.
- `scripts/retrieval/audit_embedding_tokens.py`: audits native/cached model limits. Packaged native defaults are not necessarily the app's runtime override.
- `src/core/embeddings/embedding_service.py`: earlier fix explicitly applies configured max sequence length to the local SentenceTransformers encoder and rejects unsupported caps. App setting 512 previously left the actual all-MiniLM-L6-v2 encoder at native 256, risking silent truncation. This fix is committed; do not revert it thinking candidate experiments changed the live model.
- `scripts/retrieval/retry_document_embeddings.py`: earlier recovery rewrite uses retained parser chunks and shared embedding chunker, explicit selected document IDs, refuses ready uploads, updates status ready after vector save; preserves parser text. Do not run recovery merely to repeat a benchmark.
- `tests/test_embedding_candidates.py`: four checks, including prefixes/instructions, ACL/file scoring, overlength rejection, and duplicate page/document identity.
- `scripts/README.md` and each comparison.md contain commands and before/after explanations.

Candidate input recipes: E5 uses `query: ` and `passage: `; BGE-M3 uses no prefix; Qwen queries use the English retrieval instruction recorded in config, passages unchanged. Use the same encoder/model/revision/recipe for candidate document/query vectors. Never compare vectors from different models merely because dimensions match.

## Database and live retrieval context

Last checked 2026-10-18: Supabase had only the five VietStyle uploads, all ready, 532 vectors of dimension 384. Their IDs:

- CSV: `UPLOAD-1fb7b4e78ba24519a316b544c8ec721b`
- XLSX: `UPLOAD-53956dfa17064fd9b6f42e9e01570a20`
- PDF: `UPLOAD-644eabbe7e354e76a133477b5f9f1eb2`
- DOCX: `UPLOAD-a835b48cc18c4d1baea6c2e5c3cfc54e`
- PPTX: `UPLOAD-f7d7c1fc50b1438c8902bb0d2e48337b`

Company/scope was Commerce Demo, active knowledge base, benchmark admin role. Recheck live state before database actions; teammates can change it. The old financial upload IDs in evaluate_two_document_benchmark.py are no longer in the database. Do not restore or reindex them in Supabase just to run the saved offline pilot.

The desktop ignored .env selected `sentence-transformers/all-MiniLM-L6-v2`, local, effective cap 512; do not confuse it with the older `paraphrase-multilingual-MiniLM-L12-v2`. Database restoration reused 532 retained parser chunks, left their text unchanged, and saved 532 MiniLM vectors. Baseline snapshots and hashes are in Experiment A. Candidate vectors are separate local artifacts, never uploaded to replace the working index.

Tables: `documents`, `document_parser_chunks` (retained parser output), `document_chunks` (retrieval vectors/content); extracted tables are separate. No document-language database attribute was added for these experiments. Benchmark language maps live in frozen metadata/config; English terminology inside a Vietnamese table is not proof the whole document is English.

Production retrieval already has integrated `translated_hybrid` (commit `7ce91b0`) in `src/core/retrieval/methods/translated_hybrid.py`, `query_translator.py`, the shared retrieval service/RAG/app. It combines original dense with bilingual lexical searches; optional verified `document_languages` maps scope lexical branches, and no map means bilingual searches within the same authorized document scope. Translation failures have explicit dense fallback diagnostics. Document ID, ACL, company, readiness/knowledge-base filters matter. Current embedding experiments deliberately use DENSE ONLY to isolate encoder behavior; translated hybrid has not been reevaluated with these new candidate encoders.

Main refactored document processing into readers/pipelines and split parser chunks from embedding chunks. Existing production tokenization/chunking code is under `src/core/tokenization/` (`token_counter.py`, `embedding_chunker.py`). Inspect/reuse it before designing another chunking system. Table chunking already repeats some section/table/column headers, but very long headers/rows and model-specific token limits still need care.

## Agreed production chunking direction (not newly implemented)

Do NOT turn the experimental 60-word rule into a production standard. After selecting a model, count tokens with its exact tokenizer, include model-required prefixes/special tokens, and split overlong content before encoding. Prefer sentence/section boundaries; split tables by row groups and repeat necessary table/column headers; handle a single overlong row explicitly. Keep document/page/parent/neighbor metadata so retrieval can expand context after selecting a small chunk. Detect/reject silent truncation. Changing chunking means rebuilding vectors and revisiting relevance labels, not reusing stale chunk IDs.

## Laptop: what can be done without GPU/credentials

Start by pulling Huy and reading both saved comparison reports/JSON. The corpus, results and vectors are committed, so inspect/recompute saved cosine rankings locally without downloading model weights or connecting to Supabase. Do not assume the laptop has the desktop's HF caches, GPU, Python environment, Tesseract or .env. Do not copy secrets into a note or commit them.

If actually running code, inspect the existing environment first. Project uses uv/uv.lock, Python >=3.11 (`uv sync --frozen` if a new environment is needed). On Linux/WSL, focused checks:

```bash
.venv/bin/python -m unittest discover -s tests -p test_embedding_candidates.py
```

The candidate runner supports `--device cpu` explicitly if no CUDA; CPU can be slow. `HF_HUB_OFFLINE=1` only works after the required pinned models/tokenizers have been cached on THAT machine. Without it, Hugging Face downloads are allowed by the runner, so explain storage/network impact before initiating optional heavy reruns. No model-inference API is needed. Use fresh `--output-dir` for repeats to preserve committed evidence.

Example AFTER the model is cached, not a command to run automatically:

```bash
HF_HUB_OFFLINE=1 OMP_NUM_THREADS=4 MKL_NUM_THREADS=4 .venv/bin/python scripts/retrieval/evaluate_embedding_candidates.py --snapshot artifacts/evaluation/four-direction-20261018 --model multilingual-e5-base --revision d128750597153bb5987e10b1c3493a34e5a4502a --device cpu --batch-size 2 --output-dir artifacts/evaluation/four-direction-20261018/laptop-rerun-e5
```

Other pinned revisions: BGE-M3 `5617a9f61b028005a4858fdac845db406aefb181`; Qwen3-0.6B `97b0c614be4d77ee51c0cef4e5f07c00f9eb65b3`; English E5-large-v2 `f169b11e22de13617baa190a028a32f3493550b6`.

Known inherited main test failures previously reproduced on clean main include stale imports of removed processors/app models and stale SQL expectations; do not claim the full suite is green. Target checks relevant to the actual changes are documented in the reports.

## Next session checklist

1. Read this and the two reports; check branch/worktree before edits. Avoid replaying completed benchmarks by default.
2. If the English VietStyle set has arrived, verify its semantic/numeric/table alignment, question translations and evidence labels against VN. Preserve a versioned frozen dataset. Decide scope explicitly so a same-language duplicate cannot mask cross-language failure.
3. Inspect existing production token-aware/table chunking and propose the smallest justified change. Explain it before/after for the user.
4. Run a controlled four-direction comparison on equivalent data, record chunking/tokenizer/prefixes/model revisions and metric definitions. Separate encoder-only dense tests from translated-hybrid pipeline tests.
5. Choose a model only after assessing both language directions, retrieval evidence quality, latency/VRAM and deployment constraints. Any live vector migration is a separate authorized task.
