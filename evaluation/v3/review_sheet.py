"""Write REVIEW-<set>.md: each item with its expected answer and the gold passage text, for human review.

Usage: python evaluation/v3/review_sheet.py <chunks.jsonl> dev|test
"""
import json
import sys
from pathlib import Path

HERE = Path("artifacts/evaluation/vietstyle-v3")
SHORT = {"VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf": "VN", "VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf": "EN"}


def main(chunks_path, name):
    corpus = {(r["document_name"], r["chunk_index"]): r["content"] for r in map(json.loads, open(chunks_path, encoding="utf-8"))}
    items = json.load(open(HERE / f"{name}-v3.json", encoding="utf-8"))["items"]
    lines = [f"# Review: vietstyle-{name}-v3 ({len(items)} items)", "",
             "For each item, check: is the question natural? Does the expected answer match the gold passage? "
             "Is anything missing or wrong? Mark **OK** or write the change next to the id.", ""]
    category = None
    for item in items:
        if item["category"] != category:
            category = item["category"]
            lines += [f"## {category}", ""]
        lines.append(f"### {item['id']} · role `{item['role']}` · {item['language']} · expected **{item['expected_outcome']}**")
        for turn in item["history"]:
            lines.append(f"> (previous turn) **Q:** {turn['question']}  \n> **A:** {turn['answer']}")
        lines += [f"**Q:** {item['question']}", "", f"**Expected:** {item['reference_answer']}"]
        if item["must_include"]:
            lines.append(f"- must include: {' · '.join('`' + m + '`' for m in item['must_include'])}")
        if item["must_not_include"]:
            lines.append(f"- must not include: {' · '.join('`' + m + '`' for m in item['must_not_include'])}")
        if item.get("forbidden_documents"):
            lines.append(f"- must not use: {', '.join(item['forbidden_documents'])}")
        for gold in item["gold"]:
            if gold["grade"] != 2:
                continue
            text = corpus[(gold["document"], gold["chunk_index"])].replace("\n", " ")
            text = text.split(" ", 1)[1] if text.startswith("Section:") else text
            label = SHORT.get(gold["document"], gold["document"][:24])
            lines.append(f"- gold {label}#{gold['chunk_index']}: _{text[:420]}_")
        lines += ["", "Review: ", ""]
    (HERE / f"REVIEW-{name}.md").write_text("\n".join(lines), encoding="utf-8")
    print("wrote", HERE / f"REVIEW-{name}.md")


if __name__ == "__main__":
    main(*sys.argv[1:3])
