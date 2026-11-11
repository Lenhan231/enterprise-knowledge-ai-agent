"""Draw a stratified 20-verdict sample from the test-set-2 runs and write a blind human grading sheet."""
import json
import random
import sys
from collections import Counter
from pathlib import Path

base = Path(sys.argv[1])  # artifacts/evaluation/vietstyle-test-v2
SEED = 20261111
RUNS = [("B2-before", "before"), ("B2-after", "after"), ("E2E-K-before", "before"), ("E2E-K-after", "after")]
PER_RUN = 5

qdoc = json.loads((base / "questions.json").read_text(encoding="utf-8"))
qs = {q["id"]: q for q in (qdoc.get("questions") or qdoc.get("cases"))}


def load_verdicts(name):
    out = {}
    for line in (base / "runs" / name).read_text(encoding="utf-8").splitlines():
        if line.strip():
            v = json.loads(line)
            out[(v["arm"], v["id"], v["answer_sha256"])] = v["verdict"]["correctness"]
    return out


rng = random.Random(SEED)
sample, pool_counts = [], {}
for run, phase in RUNS:
    scored = json.loads((base / "runs" / f"{run}.scored.json").read_text(encoding="utf-8"))
    raw = json.loads((base / "runs" / f"{run}.json").read_text(encoding="utf-8"))
    answers = {r["id"]: r.get("answer", "") for r in raw["results"]}
    vb = load_verdicts(f"judge-verdicts-codex-testv2-{phase}-iso.jsonl")
    vc = load_verdicts(f"judge-verdicts-claude-testv2-{phase}.jsonl")
    arm = scored["arm"]
    pool = []
    for r in scored["rows"]:
        if not isinstance(r.get("judge"), dict):
            continue  # rule-scored or skipped
        key = (arm, r["id"], r["answer_sha256"])
        a = r["judge"]["correctness"]
        b, c = vb.get(key), vc.get(key)
        if b is None or c is None:
            continue
        votes = Counter([a, b, c])
        top, n = votes.most_common(1)[0]
        majority = top if n >= 2 else "partial"
        pool.append({"run": run, "arm": arm, "id": r["id"], "sha": r["answer_sha256"],
                     "A": a, "B": b, "C": c, "majority": majority, "answer": answers.get(r["id"], "")})
    pool_counts[run] = Counter(p["majority"] for p in pool)
    # Stratify by majority grade: one non-correct first when available, then fill proportionally at random.
    by = {g: [p for p in pool if p["majority"] == g] for g in ("correct", "partial", "incorrect")}
    for g in by:
        rng.shuffle(by[g])
    picked = []
    for g in ("incorrect", "partial"):
        if by[g] and len(picked) < 2:
            picked.append(by[g].pop())
    rest = [p for g in by for p in by[g]]
    rng.shuffle(rest)
    picked += rest[: PER_RUN - len(picked)]
    sample += picked

rng.shuffle(sample)  # hide run order from the grader
for n, s in enumerate(sample, 1):
    s["n"] = n

lines = [
    "# Kiểm tra judge — vietstyle-test-v2 (20 câu, chấm mù)",
    "",
    "Với mỗi câu, đọc câu hỏi, đáp án tham chiếu, các ý bắt buộc và câu trả lời của hệ thống, rồi điền **Người chấm**: "
    "`đúng`, `một phần` hoặc `sai`, kèm ghi chú nếu cần. Đúng = truyền đạt đủ ý của đáp án tham chiếu, không có thông tin sai hay bịa; "
    "khác chữ do dịch vẫn tính đúng. Câu cần từ chối (ngoài phạm vi, bẫy): từ chối hoặc nói tài liệu không có thông tin là đúng. "
    "Câu trả lời bị chặn (\"không thể xác minh\") với câu trả lời được là sai.",
    "",
    "Bảng này **không** ghi kết quả của judge và không ghi cấu hình (trước/sau cải tiến), để người chấm không bị ảnh hưởng. "
    "Khoá đối chiếu nằm trong `judge-review-20261111.key.json`; chỉ mở sau khi chấm xong.",
    "",
    f"Chọn mẫu: 5 câu mỗi lần chạy (B2-before, B2-after, E2E-K-before, E2E-K-after), phân tầng theo kết quả đa số của 3 judge, "
    f"ưu tiên lấy ít nhất một câu không đúng mỗi lần chạy nếu có; seed {SEED}. Thứ tự câu đã được xáo trộn.",
    "",
]
for s in sample:
    q = qs[s["id"]]
    must = q.get("must_include") or []
    lines += [f"## {s['n']}. {s['id']} ({q['type']})", "",
              f"**Câu hỏi:** {q['question']}", "",
              f"**Đáp án tham chiếu:** {q['reference_answer']}", ""]
    if must:
        lines += ["**Ý bắt buộc:** " + "; ".join(str(m) for m in must), ""]
    if q.get("should_abstain"):
        lines += ["**Câu này cần từ chối.**", ""]
    ans = (s["answer"] or "").strip() or "(không có câu trả lời)"
    lines += ["**Câu trả lời của hệ thống:**", ""] + ["> " + l if l else ">" for l in ans.splitlines()] + ["",
              "**Người chấm:** ", "", "---", ""]

out = base / "judge-review-20261111.md"
out.write_text("\n".join(lines), encoding="utf-8")
key = {"seed": SEED, "per_run": PER_RUN, "pool_majority_counts": {k: dict(v) for k, v in pool_counts.items()},
       "items": [{k: s[k] for k in ("n", "run", "arm", "id", "sha", "A", "B", "C", "majority")} for s in sample]}
(base / "judge-review-20261111.key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
print("sample majority mix:", dict(Counter(s["majority"] for s in sample)))
print("pool majority mix per run:", {k: dict(v) for k, v in pool_counts.items()})
print("judge disagreements in sample:", sum(1 for s in sample if len({s['A'], s['B'], s['C']}) > 1))
print("wrote", out)
