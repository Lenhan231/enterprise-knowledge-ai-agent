"""Assign VietStyle policy topics to dev-v3 or test-v3; VN and EN copies of a topic always go together.

Usage: python evaluation/v3/build_split.py <chunks.jsonl> <split.json>
"""
import json
import sys

VN, EN = "VietStyle_Enterprise_Operating_Policy_v1.0_VN.pdf", "VietStyle_Enterprise_Operating_Policy_v1.0_EN.pdf"
# Repeated sub-headings inside every topic; they never start a new topic.
SUB = {"Quy trình bắt buộc", "Yêu cầu kiểm soát", "Bằng chứng bắt buộc", "Sự phù hợp hệ thống và dữ liệu",
       "Điều kiện chặn bổ sung bắt buộc", "Required procedure", "Control requirements", "Required evidence",
       "System and data alignment", "Additional mandatory blocks", "?"}
FRONT = 5  # cover, title, contents, hierarchy note, database note: no gold passages are taken from these
# Domain groups by topic position (0-based after FRONT); topics alternate dev/test inside each group.
GROUPS = [("governance", 4), ("leave_attendance", 6), ("expenses", 4), ("procurement", 10), ("inventory", 12),
          ("security", 8), ("exceptions_governance", 6), ("appendices", 4)]
FORCED = {"Hạn mức chi phí, ăn uống và công tác": "test"}  # holds all of fact F1
SHARED = {"Tìm nguồn cạnh tranh và đánh giá báo giá", "Ma trận phê duyệt và ngưỡng tiền",
          "Phụ lục B - Hạn mức phê duyệt và bảng quyết định vận hành"}  # split by fact tier, see SPEC.md


def topics(rows, document):
    out, current = [], None
    for row in sorted((r for r in rows if r["document_name"] == document), key=lambda r: r["chunk_index"]):
        title = (row["metadata"] or {}).get("section_title") or "?"
        if title not in SUB and (current is None or title != current["title"]):
            current = {"title": title, "indices": []}
            out.append(current)
        if current:
            current["indices"].append(row["chunk_index"])
    return out


def main(chunks_path, out_path):
    rows = [json.loads(line) for line in open(chunks_path, encoding="utf-8")]
    vn, en = topics(rows, VN), topics(rows, EN)
    assert len(vn) == len(en), (len(vn), len(en))
    body = list(zip(vn, en))[FRONT:]
    assert sum(size for _, size in GROUPS) == len(body), (sum(size for _, size in GROUPS), len(body))
    assignment, position = [], 0
    for group, size in GROUPS:
        turn = 0
        for vn_topic, en_topic in body[position:position + size]:
            if vn_topic["title"] in SHARED:
                split = "shared_by_fact"
            elif vn_topic["title"] in FORCED:
                split = FORCED[vn_topic["title"]]
            else:
                split = ("dev", "test")[turn % 2]
                turn += 1
            assignment.append({"group": group, "split": split, "title_vn": vn_topic["title"], "title_en": en_topic["title"],
                               "vn": vn_topic["indices"], "en": en_topic["indices"]})
        position += size
    # Inventory policy pack: whole documents or Planner sheets per split; the 424-row data sheet alternates rows.
    pack = {"dev": [], "test": []}
    for row in sorted(rows, key=lambda r: (r["document_name"], r["chunk_index"])):
        name, sheet = row["document_name"], (row["metadata"] or {}).get("sheet_name")
        if name.startswith(("01_", "03_")) or (name.startswith("04_") and sheet in {"Policy Matrix", "KPI Summary"}):
            split = "dev"
        elif name.startswith(("02_", "05_")) or (name.startswith("04_") and sheet in {"Exception Log", "README"}):
            split = "test"
        elif name.startswith("04_") and sheet == "Inventory Control":
            split = ("dev", "test")[row["chunk_index"] % 2]
        else:
            continue
        pack[split].append([name, row["chunk_index"]])
    json.dump({"documents": {"vn": VN, "en": EN}, "topics": assignment, "pack": pack},
              open(out_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("pack:", {k: len(v) for k, v in pack.items()})
    for item in assignment:
        print(f'{item["split"]:15s} {item["group"]:22s} VN {item["vn"][0]:3d}-{item["vn"][-1]:3d}  {item["title_vn"][:55]}')


if __name__ == "__main__":
    main(*sys.argv[1:3])
