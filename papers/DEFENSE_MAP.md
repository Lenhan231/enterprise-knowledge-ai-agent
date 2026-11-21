# Research-to-defense map

Use this file to connect papers to thesis claims. Fill **actual** implementation file paths, test commands and experiment artifacts after checking current code. Do not substitute paper benchmark scores for project results.

| Decision to defend | Relevant papers | Current repository entry points | Evidence to inspect | Likely examiner question |
| --- | --- | --- | --- | --- |
| OCR/layout pipeline | P01 | [Document processing](../src/document_processing/README.md), [Docling route](../src/document_processing/docs/docling-pipeline.md) | [OCR evaluation docs](../docs/technical/document-processing.md), [evaluation matrix](../docs/technical/agents-and-evaluation.md) | Why Docling + VietOCR/RapidOCR instead of other OCR engines? |
| Retrieval-grounded QA | P02, P03 | [RAG and retrieval architecture](../docs/technical/retrieval-rbac.md) | Labeled retrieval runs, citation validity, role filtering | How does RAG help, and when can it still hallucinate? |
| Multilingual embeddings | P04, P05 | [Embedding guide](../docs/technical/embeddings-tokenization.md) | Matched-query retrieval metrics, model and latency settings | Why this embedding model? Is reranking actually enabled? |
| Automated RAG evaluation | P06 | [Agent evaluation guide](../docs/technical/agents-and-evaluation.md) | Reproducible case hashes, human scores and tool-backed evidence | Are RAGAS/LLM-judge scores trustworthy? |
| Text-to-SQL model choice | P07, P08 | [Benchmark plan](../evaluation/agent_benchmarks/MODEL_AND_EVALUATION_PLAN.md) | Gold SQL/result equality, validator outcomes, latency, abstention | Why prompt-based SQL + guards instead of specialized fine-tuning? |

## Defense answer structure

**Problem:** What business or engineering limitation existed?

**Research:** Which cited method addresses it, under what conditions?

**Implementation:** What specifically is in *our* repository today (name the module)?

**Evidence:** Which benchmark and metric support our claim (with input/case hash, settings, version, and date)?

**Limitations:** What does this experiment *not* establish and what would we test next?

A clear, qualified answer is better than claiming the published model's scores apply directly to this system.
