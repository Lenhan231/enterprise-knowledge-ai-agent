# Groq invoice extraction — model and prompt update

Candidate source commit 36f3ed6a283351df001cb811918b889255f74f6d
Same 50 cached Kaggle VietOCR outputs and the previous normalized exact-match scoring.
The new API benchmark ran locally over cached OCR; earlier baselines ran separately.
Because both model and prompt changed, the comparison measures their combined effect.

| Model | Completed | Whole-invoice exact | Item-row exact | Mean extraction seconds |
|---|---:|---:|---:|---:|
| Qwen3-0.6B fine-tuned baseline | 50/50 | 10.0% | 96.1% | 22.33 |
| Qwen3-1.7B base baseline | 50/50 | 44.0% | 90.7% | 28.38 |
| gemini-3.5-flash-lite baseline | 50/50 | 76.0% | 96.1% | 17.45 |
| Groq GPT-OSS 20B original prompt | 50/50 | 50.0% | 96.1% | 32.61 |
| Groq GPT-OSS 120B complete-evidence prompt v2 | 50/50 | 74.0% | 96.1% | 27.69 |

Extraction times exclude cached OCR and include quota pacing/retries.

## Field accuracy

| Field | 20B original | 120B + prompt v2 |
|---|---:|---:|
| invoice_no | 70.0% | 100.0% |
| date | 100.0% | 100.0% |
| seller | 96.0% | 96.0% |
| buyer | 96.0% | 94.0% |
| subtotal | 96.0% | 100.0% |
| tax_amount | 100.0% | 100.0% |
| total_amount | 100.0% | 100.0% |

Candidate usage {'prompt_tokens': 108846, 'generated_tokens': 66161, 'requests': 50}
Estimated token cost USD 0.056023.
Rates used are USD 0.15 input and USD 0.60 output per million tokens.
Failed attempts and retries may add cost not represented by successful-result usage.
Schema-valid rate 100.0%; parse errors 0.
