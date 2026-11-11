# LLM prompts

> 2026-10-29 Report follow-up: the standalone Report interface now uses the new
> Knowledge/SQL workflow for Auto source collection (`orchestrated`; legacy
> `combined` is an alias). Dashboard remains independent. See the
> [Report integration document](../../../docs/technical/report-source-orchestration.md). The user also authorized pushing
> the completed changes to main and rebuilding local Docker. Earlier completion
> notes describe the preceding stage.

Keep executable LLM instruction templates here. Runtime modules prepare data,
format these constants, call providers, and validate results.

| File | Templates |
|---|---|
| `Knowledge.py` | Grounded document answers |
| `intent.py` | Legacy intent classification |
| `agents.py` | Task planning and repair, analytics summaries, combined-answer synthesis |
| `sql.py` | SQL generation and validation-repair instructions |
| `report.py` | Grounded report sections and repair instructions |
| `translation.py` | Automatic language detection/translation and explicit-language translation |
| `financial_extraction.py` | Page-grounded financial metric extraction |
| `evaluation.py` | RAGAS structured-judge instructions |
| `examples.py` | Groq provider smoke-test prompt |

Templates use `str.format`. Double literal JSON braces (`{{` and `}}`); keep
placeholder names aligned with callers. Data serialization and access controls
stay in the runtime modules. User questions, benchmark case data, evidence,
provider adapters, and embedding-model prefixes are not instruction templates.

The 2026-10-29 extraction moved 13 embedded templates without changing their
rendered text, including whitespace, Unicode, JSON braces, and retry suffixes.
Existing Knowledge/intent templates remain at their original paths. Benchmark
hashes and translated-Colab bundles include the newly imported prompt files.
