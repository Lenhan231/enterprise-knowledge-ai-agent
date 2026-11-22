"""Turn judge-2 labels into reviewable gold proposals (nothing is merged until a human approves).

  python evaluation/v3/pool_proposals.py <chunks.jsonl> <labels.jsonl>

Writes artifacts/evaluation/vietstyle-v3/pooled_gold.json (proposed extra gold, source "pool", approved: false)
and POOL-PROPOSALS.md (one section per item with the passage text, cross-split warnings and judge notes).
"""
import json
import sys
from pathlib import Path

HERE = Path("artifacts/evaluation/vietstyle-v3")


def main(chunks_path, labels_path):
    corpus = {(r["document_name"], r["chunk_index"]): r["content"] for r in map(json.loads, open(chunks_path, encoding="utf-8"))}
    split = json.load(open(HERE / "split.json", encoding="utf-8"))
    owner = {(split["documents"][lang], i): t["split"] for t in split["topics"] for lang in ("vn", "en") for i in t[lang]}
    owner.update({(d, i): name for name in ("dev", "test") for d, i in split["pack"][name]})
    items = {i["id"]: (name, i) for name in ("dev", "test")
             for i in json.load(open(HERE / f"{name}-v3.json", encoding="utf-8"))["items"]}
    rows = [json.loads(line) for line in open(labels_path, encoding="utf-8")]
    errors = [r["id"] for r in rows if "error" in r]
    proposals, lines = [], ["# Pooled gold proposals (judge: Groq gpt-oss-120b)", "",
                            "Approve or reject each proposed passage. Nothing is added to dev/test until approved.", ""]
    if errors:
        lines += [f"**Judge errors (not labelled):** {', '.join(errors)}", ""]
    for row in sorted((r for r in rows if "error" not in r), key=lambda r: r["id"]):
        name, item = items[row["id"]]
        found = [l for l in row["labels"] if l["grade"] > 0]
        if not found and not row["item_problem"]:
            continue
        lines.append(f"## {row['id']} ({name}, {item['category']}, expected {item['expected_outcome']})")
        lines.append(f"**Q:** {item['question']}  \n**Expected:** {item['reference_answer']}")
        if item["expected_outcome"] != "answer" and found:
            lines.append("- ⚠️ **The judge found passages for an item expected to be not covered — re-check the item.**")
        if row["item_problem"]:
            lines.append(f"- judge note: {row['item_problem']}")
        for label in found:
            key = (label["document"], label["chunk_index"])
            home = owner.get(key, "other")
            cross = home not in (name, "shared_by_fact")
            proposals.append({"id": row["id"], "set": name, "document": key[0], "chunk_index": key[1], "grade": label["grade"],
                              "why": label["why"], "home_split": home, "source": "pool", "approved": False})
            text = corpus[key].replace("\n", " ")
            text = text.split(" ", 1)[1] if text.startswith("Section:") else text
            short = key[0][-6:-4] if key[0].startswith("VietStyle") else key[0][:3]
            lines.append(f"- [ ] **grade {label['grade']}** {short}#{key[1]}{' ⚠️ belongs to ' + home + ' topics (fact appears in both sets)' if cross else ''}"
                         f" — {label['why']}  \n  _{text[:300]}_")
        lines.append("")
    json.dump(proposals, open(HERE / "pooled_gold.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    (HERE / "POOL-PROPOSALS.md").write_text("\n".join(lines), encoding="utf-8")
    by = lambda s, g: sum(1 for p in proposals if p["set"] == s and p["grade"] == g)
    print(f"{len(rows)} items judged, {len(errors)} errors; proposals dev: {by('dev', 2)}x2 {by('dev', 1)}x1, "
          f"test: {by('test', 2)}x2 {by('test', 1)}x1; cross-split: {sum(1 for p in proposals if p['home_split'] not in (p['set'], 'shared_by_fact'))}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
