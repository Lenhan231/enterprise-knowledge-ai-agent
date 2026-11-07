#!/usr/bin/env python3
"""Build local corrected English simulation documents; no database/model access."""
import csv
import hashlib
import html
import io
import json
import re
import shutil
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "artifacts/evaluation/vietstyle-bilingual-20261019"
VIETNAMESE = re.compile("[ăâđêôơưĂÂĐÊÔƠƯàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]")
NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def numeric_signature(path):
    """All spreadsheet cell coordinates, value types, formulas and stored numeric values."""
    result = {}
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                cells = []
                for c in ET.fromstring(archive.read(name)).findall(".//s:c", NS):
                    value, formula = c.find("s:v", NS), c.find("s:f", NS)
                    cells.append((c.get("r"), c.get("t"), None if value is None else value.text,
                                  None if formula is None else formula.text))
                result[name] = cells
    return result

def visible_office_text(path):
    values = []
    with zipfile.ZipFile(path) as archive:
        for name in archive.namelist():
            if name.endswith(".xml") and name.startswith(("xl/", "ppt/slides/", "word/document")):
                for node in ET.fromstring(archive.read(name)).iter():
                    if node.tag.endswith("}t") and node.text:
                        values.append(node.text)
    return values

def patch_office(source, target, translations):
    changes = []
    with zipfile.ZipFile(source) as old, zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as new:
        for entry in old.infolist():
            raw = old.read(entry)
            if entry.filename.endswith(".xml"):
                text = raw.decode("utf-8")
                def replace_text(match):
                    before = html.unescape(match.group(2))
                    after = translations.get(before)
                    if after is None:
                        return match.group(0)
                    changes.append({"part": entry.filename, "before": before, "after": after})
                    return match.group(1) + html.escape(after, quote=False) + match.group(3)
                # XML writers may encode Vietnamese as numeric entities. Match text nodes,
                # decode entities, then replace without rewriting namespace declarations.
                text = re.sub(r"(<(?:[A-Za-z0-9_]+:)?t(?:\s[^>]*)?>)(.*?)(</(?:[A-Za-z0-9_]+:)?t>)",
                              replace_text, text, flags=re.DOTALL)
                raw = text.encode("utf-8")
                ET.fromstring(raw)  # Preserve XML spelling/prefix declarations; check well-formedness.
            new.writestr(entry, raw)
    return changes

def render_sop(source, target):
    css = """body {font-family: monospace; font-size: 9.5pt; line-height: 1.23; color:#17212b;}
    h1 {font-size:20pt; color:#163652;} h2 {font-size:12pt; color:#163652; margin-top:13pt;}
    table {border-collapse:collapse; width:100%; margin:8pt 0; font-size:8.5pt;}
    th,td {border:0.6pt solid #aeb8c0; padding:5pt; vertical-align:top;}
    th {background-color:#eaf0f4;} li {margin-bottom:3pt;}"""
    story = fitz.Story(html=source.read_text(encoding="utf-8"), user_css=css)
    box = fitz.paper_rect("a4")
    content = box + (44, 42, -44, -42)
    writer = fitz.DocumentWriter(str(target))
    more = True
    while more:
        device = writer.begin_page(box)
        more, filled = story.place(content)
        story.draw(device)
        writer.end_page()
    writer.close()

def main():
    original, source = BASE / "sources/en", BASE / "translation-source"
    out = BASE / "corrected-en-v1"
    out.mkdir(exist_ok=True)
    translations = json.loads((source / "remaining-text-translations.json").read_text(encoding="utf-8"))
    changes, files = [], {}
    for path in sorted(original.iterdir()):
        target = out / path.name
        if path.suffix == ".pdf":
            render_sop(source / "sop-english.html", target)
            with fitz.open(target) as doc:
                text = "\n".join(page.get_text() for page in doc)
                normalized = re.sub(r"\s+", " ", text)
                assert not VIETNAMESE.search(text) and "\ufffd" not in text
                for phrase in ["DATA CONFLICT", "stockout_days >= 1", "fill_rate < 95%", "120 days",
                               "policy_id", "Adjustment Transaction ID", "16/10/2026", "SOP-INV-002"]:
                    assert phrase in normalized, phrase
                assert all(f"{n}. " in text for n in range(1, 9))
                files[path.name] = {"source_sha256": sha(path), "output_sha256": sha(target),
                                    "pdf_pages": len(doc), "extractable_characters": len(text),
                                    "method": "Complete assistant translation of frozen VN SOP; regenerated selectable-text PDF"}
                doc[0].get_pixmap(dpi=100).save(str(BASE / "corrected-sop-preview.png"))
            continue
        if path.suffix == ".docx":
            shutil.copyfile(path, target)
            assert sha(path) == sha(target)
        elif path.suffix in {".xlsx", ".pptx"}:
            changes.extend({"file": path.name, **change} for change in patch_office(path, target, translations))
            if path.suffix == ".xlsx":
                assert numeric_signature(path) == numeric_signature(target), "Workbook values/formulas changed"
        elif path.suffix == ".csv":
            with path.open(encoding="utf-8-sig", newline="") as handle:
                reader = csv.DictReader(handle); fields = reader.fieldnames; before = list(reader)
            after = [{key: translations.get(value, value) for key, value in row.items()} for row in before]
            with target.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields);writer.writeheader();writer.writerows(after)
            assert len(before) == len(after) == 12
            for oldrow, newrow in zip(before, after):
                assert oldrow["policy_id"] == newrow["policy_id"]
                for key in fields:
                    if oldrow[key] != newrow[key]:
                        assert key == "sla_or_frequency"
                        changes.append({"file": path.name, "policy_id": oldrow["policy_id"], "before": oldrow[key], "after": newrow[key]})
            assert not VIETNAMESE.search(target.read_text(encoding="utf-8"))
        else:
            raise ValueError(path.name)
        if path.suffix in {".docx", ".pptx", ".xlsx"}:
            leftovers = [t for t in visible_office_text(target) if VIETNAMESE.search(t)]
            assert not leftovers, (path.name, leftovers)
        files[path.name] = {"source_sha256": sha(path), "output_sha256": sha(target),
                            "method": "Unchanged English manual" if path.suffix == ".docx" else "Remaining text translated; original structure retained"}
    assert len(files) == 5
    manifest = {"version": "corrected-en-v1", "purpose": "Local simulated-data benchmark only; not an approved operational policy",
                "translation": "Assistant-created from supplied English pack and frozen Vietnamese SOP; not an independent human translation certification",
                "files": files, "changes": changes,
                "checks": {"workbook_coordinates_values_types_formulas_unchanged": True,
                           "csv_policy_ids_and_non_SLA_fields_unchanged": True,
                           "docx_byte_identical": True, "no_detected_Vietnamese_diacritics_in_visible_text": True,
                           "pdf_extractable_text_and_required_policy_markers": True},
                "limitations": "Diacritic screening is a diagnostic, not a language classifier. PDF visual inspection is separate; Office rendering not automated. Old chunk/page labels cannot be reused without alignment. No missing README policy document was invented."}
    (BASE / "english-build-manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    bundle = BASE / "VietStyle_Inventory_Documents_English_Corrected_v1.zip"
    with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(out.iterdir()):archive.write(file, file.name)
        for name in ["benchmark-questions-en-v1.json", "BUILD_NOTES.md"]:
            if (BASE / name).exists():archive.write(BASE / name, name)
    print(json.dumps({"output": str(out), "bundle": str(bundle), "files": len(files), "text_replacements": len(changes), "checks": manifest["checks"]}, indent=2))

if __name__ == "__main__":
    main()
