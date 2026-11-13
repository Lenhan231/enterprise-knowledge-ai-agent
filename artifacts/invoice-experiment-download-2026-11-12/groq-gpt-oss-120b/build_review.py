"""Build an offline invoice inspection page from completed Groq benchmark results."""
import html
import json
from pathlib import Path

folder = Path(__file__).resolve().parent
root = folder.parents[1]
results_path = folder / "results.json"
results = json.loads(results_path.read_text())
scored = results
ocr = json.loads((root / "artifacts/invoice-pilot-50-new-vietocr/ocr_results.json").read_text())
metrics = scored["metrics"]
escape = html.escape
cards = []
header_fields = metrics["header_exact_match_rates"]
for score in scored["scores"]:
    filename = score["file"]
    row = results["results"][filename]
    predicted = row.get("fields") or {}
    expected = row["expected"]
    matched = bool(score["whole_invoice_exact"])
    cells = []
    for key in header_fields:
        state = "match" if score[key + "_exact"] else "mismatch"
        expected_text = "null" if expected.get(key) is None else str(expected[key])
        predicted_text = "null" if predicted.get(key) is None else str(predicted[key])
        cells.append(
            f'<tr class="{state}"><th>{escape(key)}</th>'
            f'<td>{escape(expected_text)}</td><td>{escape(predicted_text)}</td></tr>'
        )
    sample = ocr["samples"][filename]
    ocr_text = "\n\n".join(str(element.get("text", "")) for element in sample.get("elements", []))
    expected_items = escape(json.dumps(expected.get("items", []), ensure_ascii=False, indent=2))
    predicted_items = escape(json.dumps(predicted.get("items", []), ensure_ascii=False, indent=2))
    tables = escape(json.dumps(sample.get("tables", []), ensure_ascii=False, indent=2))
    error = row.get("error") or row.get("parse_error") or ""
    conflicts = row.get("field_conflicts") or {}
    cards.append(
        f'<article data-match="{str(matched).lower()}" data-file="{escape(filename)}">'
        f'<h2>{escape(filename)} <span>{"Exact" if matched else "Needs review"}</span></h2>'
        f'<p>{escape(row["quality"])} · extraction {row["elapsed_seconds"]:.2f}s · '
        f'item rows exact {score["item_rows_exact_rate"]:.1%}</p>'
        f'<p class="error">{escape(str(error))}</p>'
        '<table><thead><tr><th>Field</th><th>Expected</th><th>Groq prediction</th></tr></thead>'
        f'<tbody>{"".join(cells)}</tbody></table>'
        '<details><summary>Line items — expected / predicted</summary><div class="columns">'
        f'<pre>{expected_items}</pre><pre>{predicted_items}</pre></div></details>'
        f'<details><summary>OCR text</summary><pre>{escape(ocr_text)}</pre></details>'
        f'<details><summary>OCR tables</summary><pre>{tables}</pre></details>'
        f'<details><summary>Field conflicts and model response</summary><pre>'
        f'{escape(json.dumps(conflicts,ensure_ascii=False,indent=2))}\n'
        f'{escape(str(row.get("raw_response") or ""))}</pre></details></article>'
    )
page = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Groq GPT-OSS 120B — prompt v2 — 50 invoice review</title>
<style>
:root{color-scheme:light}
body{max-width:1180px;margin:32px auto;padding:0 18px;background:#f4f7fb;color:#192d43;font:15px/1.6 system-ui}
h1{font-size:28px}h2{font-size:19px}h2 span{font-size:13px;color:#526478}
article{margin:20px 0;padding:22px;border:1px solid #dce4ef;border-radius:12px;background:white}
table{width:100%;border-collapse:collapse;table-layout:fixed}
td,th{padding:10px;border:1px solid #dce4ef;text-align:left;vertical-align:top;overflow-wrap:anywhere}
th{width:20%}.mismatch{background:#fff0f0}.mismatch td:last-child{color:#ae2833;font-weight:600}
.columns{display:grid;grid-template-columns:1fr 1fr;gap:14px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;max-height:500px;overflow:auto;min-width:0}
details{margin:15px 0}summary{cursor:pointer;font-weight:600}
.controls{display:flex;flex-wrap:wrap;gap:15px;padding:12px 0}
select,input{padding:8px;border:1px solid #c6d3e4;border-radius:6px;font:inherit}
.error{color:#ae2833}
@media(max-width:700px){.columns{grid-template-columns:1fr}article{padding:12px}td,th{padding:6px;font-size:12px}}
</style></head><body><h1>Groq GPT-OSS 120B — prompt v2 — 50 invoice review</h1>"""
page += (
    f'<p><strong>Whole-invoice exact {metrics["whole_invoice_exact_rate"]:.1%}</strong> · '
    f'item row exact {metrics["item_row_exact_accuracy"]:.1%} · '
    f'completed {metrics["success_count"]}/50</p>'
    '<p>Uses the same saved VietOCR evidence and normalized scoring as the previous benchmark. '
    'Whole-invoice exact requires all header fields, item counts and item fields to match, '
    'with valid JSON and no parse errors or field conflicts. Numeric values are compared by digits, '
    'text by normalized Unicode, whitespace and case, and dates allow a leading Ngày label.</p>'
    '<p>Extraction time includes API quota pacing and retries and excludes cached OCR.</p>'
    '<div class="controls"><label>Show <select id="filter"><option value="all">All invoices</option>'
    '<option value="false">Needs review</option><option value="true">Exact</option></select></label>'
    '<label>Invoice <input id="search" type="search" placeholder="invoice_0937"></label>'
    '<span id="count" aria-live="polite"></span></div>'
)
page += "".join(cards)
page += """<script>
const filter=document.querySelector('#filter');
const search=document.querySelector('#search');
function applyFilter(){
  let count=0;
  document.querySelectorAll('article').forEach(article=>{
    article.hidden=(filter.value!=='all'&&article.dataset.match!==filter.value)
      ||!article.dataset.file.toLowerCase().includes(search.value.trim().toLowerCase());
    if(!article.hidden)count++;
  });
  document.querySelector('#count').textContent=count+' / 50 invoices';
}
filter.onchange=applyFilter;
search.oninput=applyFilter;
applyFilter();
</script></body></html>"""
output = folder / "groq120b-review.html"
output.write_text(page, encoding="utf-8")
print(output)
