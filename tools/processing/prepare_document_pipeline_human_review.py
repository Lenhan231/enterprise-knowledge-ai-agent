"""Prepare prediction-blind review pages for locked-test labels and reading order."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/document-pipelines"
LAYOUT_REFERENCE = ROOT / "data/evaluation/layout/vn-enterprise-layout-v2-adjudicated-reference.json"
ORDER_REFERENCE = ROOT / "data/evaluation/layout/vn-enterprise-reading-order-reference.json"
OCR_REFERENCE = BASE / "ocr/reference/reference.csv"
TABLE_REFERENCE = BASE / "tables/reference/reference.jsonl"
COLORS = {"title": "red", "text": "dodgerblue", "table": "limegreen", "figure": "magenta"}


def write_review_page(output: Path, title: str, task: str, items: list[dict[str, Any]], field_specs: list[tuple[str, str]]) -> None:
    payload = json.dumps(items, ensure_ascii=False).replace("</", "<\\/")
    specs = json.dumps(field_specs, ensure_ascii=False)
    review_note = (
        "Cleaner-output-blind review. The source page, native text, and raw OCR spans are shown because those spans must be classified; the final deduplicated/filtered output is hidden."
        if task == "cleaning"
        else "Prediction-blind review packet. It contains source images and reference annotations only; no PP-StructureV3, MinerU, or Docling predictions are included. Check each item against the image, edit the fields, mark it reviewed, then export the JSON."
    )
    page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:16px system-ui,sans-serif;margin:24px auto;max-width:1200px;padding:0 16px;color:#172033;background:#f5f7fb}}
h1{{font-size:1.5rem}} .note{{background:#fff6d8;padding:12px;border-radius:8px}}
.toolbar{{position:sticky;top:0;background:#f5f7fb;padding:10px 0;z-index:2;display:flex;gap:12px;align-items:center}}
article{{background:white;margin:18px 0;padding:16px;border:1px solid #d9e0ea;border-radius:10px}}
.item{{display:grid;grid-template-columns:minmax(300px, 48%) 1fr;gap:18px;align-items:start}}
img{{max-width:100%;height:auto;border:1px solid #ccd3df;background:white}} label{{display:block;font-weight:600;margin:10px 0 4px}}
textarea{{box-sizing:border-box;width:100%;min-height:150px;font:13px ui-monospace,monospace;padding:10px}}
.cleaning-spans{{max-height:520px;overflow:auto;border:1px solid #d9e0ea;border-radius:6px}}
.cleaning-span{{display:grid;grid-template-columns:minmax(180px,1fr) auto 180px;gap:12px;align-items:center;padding:8px;border-bottom:1px solid #e8ecf2}}
.cleaning-span select{{padding:6px;max-width:100%}}
button{{padding:10px 16px;background:#1459bd;color:white;border:0;border-radius:6px;cursor:pointer}}
@media(max-width:760px){{.item{{grid-template-columns:1fr}}}}
</style></head><body>
<h1>{html.escape(title)}</h1><p class="note">{html.escape(review_note)}</p>
<div class="toolbar"><label>Reviewer ID <input id="reviewer" autocomplete="off"></label><button id="export">Export reviewed JSON</button><span id="count"></span></div>
<main id="items"></main>
<script>
const task={json.dumps(task)}, items={payload}, specs={specs};
const escapeHtml=s=>String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
const main=document.querySelector('#items');
for(const item of items){{
 const article=document.createElement('article');
 let fields='';
 if(task==='cleaning') {{
  const spans=JSON.parse(item.reviewed_ocr_spans_json||'[]');
  const rows=spans.map((span,index)=>`<div class="cleaning-span"><textarea data-span-text rows="2" readonly aria-label="OCR span ${{index+1}}">${{escapeHtml(span.text)}}</textarea><button type="button" data-split-span title="Split this OCR span at the cursor into separately labeled spans">Split at cursor</button><select data-span-index="${{index}}" aria-label="Classify OCR span ${{index+1}}"><option value="">Choose label</option><option value="new_valid">New valid content</option><option value="duplicate">Already in native text</option><option value="noise">OCR noise</option></select></div>`).join('');
  fields=`<label>Native PDF text context (read-only)</label><textarea data-field="native_text_context" readonly>${{escapeHtml(item.native_text_context??'')}}</textarea><label>OCR spans — classify each against the source image</label><p>If one span mixes content types, focus its text and use “Split at cursor” at each boundary; then label the pieces separately.</p>${{spans.length?`<div class="cleaning-spans">${{rows}}</div>`:'<p>No OCR spans were returned for this page. Verify the marked region against the source and mark the page reviewed only if appropriate.</p>'}}`;
 }} else {{
  for(const [key,label] of specs) {{
   const readonly=task==='reading-order' && key==='reference_blocks_json' ? 'readonly' : '';
   fields+=`<label>${{escapeHtml(label)}}</label><textarea data-field="${{escapeHtml(key)}}" ${{readonly}}>${{escapeHtml(item[key]??'')}}</textarea>`;
  }}
 }}
 article.innerHTML=`<h2>${{escapeHtml(item.id)}} <small>${{escapeHtml(item.split??'')}}</small></h2><div class="item"><a href="${{escapeHtml(item.image)}}" target="_blank"><img loading="lazy" src="${{escapeHtml(item.image)}}" alt="${{escapeHtml(item.id)}} source"></a><div>${{fields}}<label><input type="checkbox" data-reviewed> Reviewed against source image</label><label>Review note</label><textarea data-note></textarea></div></div>`;
 main.append(article);
 if(task==='cleaning') {{
  const container=article.querySelector('.cleaning-spans');
  if(container) container.addEventListener('click',event=>{{
   const button=event.target.closest('[data-split-span]');
   if(!button) return;
   const row=button.closest('.cleaning-span');
   const textArea=row.querySelector('[data-span-text]');
   const position=textArea.selectionStart;
   const text=textArea.value;
   const left=text.slice(0,position), right=text.slice(position);
   if(!left.trim() || !right.trim()) {{ alert('Place the cursor between two nonempty text parts before splitting.'); return; }}
   const index=Number(row.querySelector('select').dataset.spanIndex);
   const current=[...container.querySelectorAll('.cleaning-span')].map(currentRow=>({{
    text:currentRow.querySelector('[data-span-text]').value,
    classification:currentRow.querySelector('select').value
   }}));
   current.splice(index,1,{{text:left,classification:''}},{{text:right,classification:''}});
   container.innerHTML=current.map((span,i)=>`<div class="cleaning-span"><textarea data-span-text rows="2" readonly aria-label="OCR span ${{i+1}}">${{escapeHtml(span.text)}}</textarea><button type="button" data-split-span title="Split this OCR span at the cursor into separately labeled spans">Split at cursor</button><select data-span-index="${{i}}" aria-label="Classify OCR span ${{i+1}}"><option value="">Choose label</option><option value="new_valid" ${{span.classification==='new_valid'?'selected':''}}>New valid content</option><option value="duplicate" ${{span.classification==='duplicate'?'selected':''}}>Already in native text</option><option value="noise" ${{span.classification==='noise'?'selected':''}}>OCR noise</option></select></div>`).join('');
  }});
 }}
}}
document.querySelector('#count').textContent=`${{items.length}} items`;
document.querySelector('#export').addEventListener('click',()=>{{
 const reviewer=document.querySelector('#reviewer').value.trim();
 const rows=[...main.querySelectorAll('article')].map((article,index)=>{{
  const values={{}};
  if(task==='cleaning') {{
   values.native_text_context=article.querySelector('[data-field="native_text_context"]').value;
   const spans=[...article.querySelectorAll('.cleaning-span')].map(row=>({{
    source:'ocr',text:row.querySelector('[data-span-text]').value,
    classification:row.querySelector('select[data-span-index]').value
   }}));
   values.reviewed_ocr_spans_json=JSON.stringify(spans);
  }} else article.querySelectorAll('textarea[data-field]').forEach(el=>values[el.dataset.field]=el.value);
  return {{id:items[index].id,split:items[index].split??null,reviewed:article.querySelector('[data-reviewed]').checked,reviewer,review_note:article.querySelector('[data-note]').value,...values}};
 }});
 const invalid=rows.find(row=>{{
  if(!row.reviewed) return false;
  if(!reviewer) return true;
  try {{
   if(task==='ocr') return !row.reviewed_transcript.trim();
   if(task==='tables') {{ const grid=JSON.parse(row.reviewed_cell_grid_json); return !Array.isArray(grid) || !row.reviewed_html.toLowerCase().includes('<table'); }}
   if(task==='layout') return !Array.isArray(JSON.parse(row.reviewed_annotations_json));
   if(task==='cleaning') {{
    const ocr=JSON.parse(row.reviewed_ocr_spans_json), ocrLabels=new Set(['new_valid','duplicate','noise']);
    return !Array.isArray(ocr) || ocr.some(span=>!span.text?.trim() || !ocrLabels.has(span.classification));
   }}
   if(task==='reading-order') {{
    const expected=JSON.parse(row.reference_blocks_json).map(block=>block.annotation_index).sort((a,b)=>a-b);
    const order=row.ordered_annotation_indices.split(',').map(value=>Number(value.trim()));
    return order.length!==expected.length || new Set(order).size!==expected.length || order.slice().sort((a,b)=>a-b).some((value,i)=>value!==expected[i]);
   }}
  }} catch(e) {{ return true; }}
  return false;
 }});
 if(invalid) {{ alert(`Item ${{invalid.id}} is marked reviewed but has missing/invalid fields. Reviewer ID is required for reviewed items.`); return; }}
 const payload={{task,dataset_id:items[0]?.dataset_id??null,reviewed_items:rows}};
 if(task==='cleaning') payload.review_provenance='human_review';
 const blob=new Blob([JSON.stringify(payload,null,2)],{{type:'application/json'}});
 const link=document.createElement('a');link.href=URL.createObjectURL(blob);link.download=`${{task}}-review-results.json`;link.click();URL.revokeObjectURL(link.href);
}});
</script></body></html>'''
    output.write_text(page, encoding="utf-8")


def render_pdf(pdf_path: Path, output: Path, dpi: int = 180) -> None:
    with fitz.open(pdf_path) as document:
        if len(document) != 1:
            raise ValueError(f"Expected single-page crop {pdf_path}; got {len(document)} pages")
        pix = document[0].get_pixmap(dpi=dpi, alpha=False)
        image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=91, optimize=True)
    image.close()


def current_layout_overlay(page: dict[str, Any], source: Path, output: Path) -> None:
    image = Image.open(source).convert("RGB")
    draw = ImageDraw.Draw(image)
    width = max(2, image.width // 700)
    for index, annotation in enumerate(page.get("annotations", [])):
        x0, y0, x1, y1 = annotation["bbox_xyxy"]
        color = COLORS.get(annotation["class"], "orange")
        draw.rectangle((x0, y0, x1, y1), outline=color, width=width)
        label = str(index)
        bounds = draw.textbbox((x0, y0), label)
        draw.rectangle(bounds, fill=color)
        draw.text((x0, y0), label, fill="white")
    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output, "JPEG", quality=88, optimize=True)
    image.close()


def html_table(grid: list[list[str]]) -> str:
    rows = []
    for row in grid:
        rows.append("<tr>" + "".join(f"<td>{html.escape(str(cell))}</td>" for cell in row) + "</tr>")
    return "<table>" + "".join(rows) + "</table>"


def build(output: Path) -> dict[str, int]:
    if output.exists():
        raise FileExistsError(f"Refusing to overwrite human-review packet: {output}")
    output.mkdir(parents=True)
    counts: dict[str, int] = {}

    # OCR test transcripts: only source crops and current reference text are shown.
    ocr_dir = output / "ocr"
    ocr_items = []
    with OCR_REFERENCE.open(encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            if row.get("split") != "locked_test":
                continue
            sample_id = row["sample_id"]
            input_pdf = BASE / "ocr/reference/inputs" / f"{sample_id}.pdf"
            image_rel = f"images/{sample_id}.jpg"
            render_pdf(input_pdf, ocr_dir / image_rel)
            ocr_items.append({
                "id": sample_id,
                "split": row["split"],
                "dataset_id": "vietnam-enterprise-ocr-500-crops-v1",
                "issuer": row.get("issuer"),
                "document_id": row.get("document_id"),
                "image": image_rel,
                "reviewed_transcript": row.get("corrected_transcript", ""),
            })
    write_review_page(ocr_dir / "review.html", "OCR locked-test reference review", "ocr", ocr_items,
                      [("reviewed_transcript", "Transcript to retain/correct (Vietnamese diacritics and punctuation) ")])
    counts["ocr_locked_test"] = len(ocr_items)

    # Table crops: current grid is visible for correction; no model table output is present.
    table_dir = output / "tables"
    table_items = []
    table_rows = [json.loads(line) for line in TABLE_REFERENCE.read_text(encoding="utf-8").splitlines() if line.strip()]
    for row in table_rows:
        if row.get("split") != "locked_test":
            continue
        table_id = row["reference_id"]
        image_rel = f"images/{table_id}.jpg"
        render_pdf(BASE / "tables/reference/inputs" / f"{table_id}.pdf", table_dir / image_rel)
        grid = row["cell_grid"]
        table_items.append({
            "id": table_id,
            "split": row["split"],
            "dataset_id": "vietnam-enterprise-table-reference-v1",
            "issuer": row.get("issuer"),
            "image": image_rel,
            "reviewed_cell_grid_json": json.dumps(grid, ensure_ascii=False, indent=2),
            "reviewed_html": html_table(grid),
        })
    write_review_page(table_dir / "review.html", "Table locked-test reference review", "tables", table_items,
                      [("reviewed_cell_grid_json", "Cell grid JSON to retain/correct"),
                       ("reviewed_html", "HTML structure; correct rowspan/colspan for merged cells")])
    counts["tables_locked_test"] = len(table_items)

    # Layout reference boxes and reading-order labels use the same source pages.
    layout_dir = output / "layout"
    layout_reference = json.loads(LAYOUT_REFERENCE.read_text(encoding="utf-8"))
    order_reference = json.loads(ORDER_REFERENCE.read_text(encoding="utf-8"))
    layout_items = []
    order_items = []
    order_by_id = {row["page_id"]: row for row in order_reference["pages"]}
    for page in layout_reference["pages"]:
        if page.get("split") not in {"validation", "locked_test"}:
            continue
        page_id = page["page_id"]
        image_source = ROOT / page["image_file"]
        image_rel = f"images/{page_id}.jpg"
        image_target = layout_dir / image_rel
        current_layout_overlay(page, image_source, image_target)
        annotations = [
            {"annotation_index": index, "class": annotation["class"], "bbox_xyxy": annotation["bbox_xyxy"]}
            for index, annotation in enumerate(page.get("annotations", []))
        ]
        if page.get("split") == "locked_test":
            layout_items.append({
                "id": page_id,
                "split": page["split"],
                "dataset_id": layout_reference["dataset_id"],
                "image": image_rel,
                "reviewed_annotations_json": json.dumps(annotations, ensure_ascii=False, indent=2),
            })
        # No existing order is prefilled for validation/test; the numbered image
        # identifies reference boxes only and contains no parser output/order.
        existing_order = order_by_id.get(page_id)
        if page["split"] in {"validation", "locked_test"}:
            order_items.append({
                "id": page_id,
                "split": page["split"],
                "dataset_id": order_reference["dataset_id"],
                "image": image_rel,
                "reference_blocks_json": json.dumps(annotations, ensure_ascii=False, indent=2),
                "ordered_annotation_indices": ",".join(map(str, existing_order.get("ordered_annotation_indices", []))) if existing_order else "",
                "ordering_note": existing_order.get("ordering_note", "") if existing_order else "",
            })
    write_review_page(layout_dir / "layout-test-review.html", "Layout locked-test reference review", "layout", layout_items,
                      [("reviewed_annotations_json", "Reference annotations JSON to retain/correct; boxes use source-image pixel coordinates")])
    write_review_page(layout_dir / "reading-order-validation-test-review.html", "Reading-order validation/test review", "reading-order", order_items,
                      [("reference_blocks_json", "Numbered reference blocks and coordinates (read-only source)",),
                       ("ordered_annotation_indices", "Enter annotation indices in reading order, comma-separated"),
                       ("ordering_note", "Short note for multi-column/table reading order, if needed")])
    counts["layout_locked_test"] = len(layout_items)
    counts["reading_order_validation_test"] = len(order_items)

    readme = """# Prediction-blind human review packet

This packet contains source crop/page images and reference labels only. It does not contain PP-StructureV3, MinerU, or Docling predictions.

## Review pages

- `ocr/review.html`: check 101 locked-test OCR transcripts against each crop.
- `tables/review.html`: check 32 locked-test cell grids and enter corrected HTML with `rowspan`/`colspan` for merged cells.
- `layout/layout-test-review.html`: review the 40 locked-test reference boxes. The numbered colored outlines show current assistant-adjudicated labels; numbers are annotation indices.
- `layout/reading-order-validation-test-review.html`: assign reading order to the 39 validation and 40 locked-test pages using numbered reference blocks. Existing order for those splits is blank.

Enter a reviewer ID, inspect every item, mark it reviewed, and use **Export reviewed JSON**. Review labels against the image without opening pipeline outputs. Keep exported files as review evidence; merge only completed items into canonical references after a second consistency check. Do not mark an item reviewed if uncertain; add a note and leave it unchecked.

The current text/boxes/grids are assistant-adjudicated starting references, not human ground truth. Test scores from the untuned pipeline have already been inspected, so any later test comparison remains retrospective rather than a pristine confirmatory test.
"""
    (output / "README.md").write_text(readme, encoding="utf-8")
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "human-review")
    args = parser.parse_args()
    output = args.output if args.output.is_absolute() else ROOT / args.output
    counts = build(output)
    print(json.dumps({"output": str(output), "counts": counts}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
