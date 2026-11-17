"""Deterministic answer scoring for v3 runs (SPEC.md): outcome, required facts, wrong seals, wrongly withheld, leaks.

  python evaluation/v3/score_answers.py <dev|test> <answers.jsonl> [...] [--json out.json]

Outcome per item: sealed (claim check supported), unverified (audit failed, draft shown), withheld (claim check rejected
or unavailable), not_covered (insufficient context), answered (no claim check ran).
"""
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parents[2] / "artifacts/evaluation/vietstyle-v3"
SHOWN = {"sealed", "unverified", "answered"}


def normalize(text):
    return unicodedata.normalize("NFC", text).casefold()


def contains(answer, alternative):
    """Whole-number rule: '7' never matches inside '17'; other text matches as a case-insensitive substring."""
    alt = normalize(alternative.strip())
    if re.fullmatch(r"[\d.,]+", alt):
        return re.search(rf"(?<![\d.,]){re.escape(alt)}(?![\d]|[.,]\d)", answer) is not None
    return alt in answer


def outcome(row):
    check = row.get("verification") or {}
    if row.get("insufficient_context"):
        return "not_covered"
    if not check:
        return "answered"
    if check.get("status") == "supported":
        return "sealed"
    return "unverified" if check.get("audit_failed") else "withheld"


def judge(item, row):
    shown = outcome(row)
    answer = normalize(row.get("answer") or "")
    facts_ok = all(any(contains(answer, alt) for alt in entry.split("|")) for entry in item["must_include"])
    forbidden_text = any(any(contains(answer, alt) for alt in entry.split("|")) for entry in item["must_not_include"])
    leak = any(c["document"] in item["forbidden_documents"] for c in row.get("cited", []))
    if item["expected_outcome"] == "answer":
        correct = shown in SHOWN and facts_ok and not forbidden_text
    else:  # not_covered / clarify: nothing from the documents should be presented as the answer
        correct = shown in ("not_covered", "withheld") and not leak
    vietnamese = len(re.findall(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", answer)) > 3
    return {"outcome": shown, "correct": correct, "facts_ok": facts_ok, "forbidden_text": forbidden_text, "leak": leak,
            # A seal on an answer that contradicts gold, or on a question the documents should not answer.
            "wrong_seal": shown == "sealed" and (forbidden_text or item["expected_outcome"] != "answer" or leak),
            # Shown and consistent with gold, but a required fact is missing.
            "incomplete": item["expected_outcome"] == "answer" and shown in SHOWN and not facts_ok and not forbidden_text,
            "language_mismatch": shown in SHOWN and (item["language"] == "en") == vietnamese,
            "wrongly_withheld": item["expected_outcome"] == "answer" and shown in ("withheld", "not_covered")}


def score(set_name, path):
    items = {i["id"]: i for i in json.load(open(HERE / f"{set_name}-v3.json", encoding="utf-8"))["items"]}
    rows = [json.loads(l) for l in open(path, encoding="utf-8") if "error" not in json.loads(l)]
    per = {r["id"]: judge(items[r["id"]], r) for r in rows}
    by_cat = defaultdict(list)
    for item_id, result in per.items():
        by_cat[items[item_id]["category"]].append(result["correct"])
    answer_items = [i for i in per if items[i]["expected_outcome"] == "answer"]
    rate = lambda ids, key: round(sum(per[i][key] for i in ids) / len(ids), 3) if ids else None
    return {"run": Path(path).stem, "items": len(rows), "accuracy": rate(list(per), "correct"),
            "answer_accuracy": rate(answer_items, "correct"),
            "not_covered_accuracy": rate([i for i in per if items[i]["expected_outcome"] != "answer"], "correct"),
            "wrong_seal_rate": rate(list(per), "wrong_seal"), "incomplete_rate": rate(answer_items, "incomplete"),
            "language_mismatch_rate": rate([i for i in per if items[i]["language"] == "en"], "language_mismatch"),
            "wrongly_withheld_rate": rate(answer_items, "wrongly_withheld"),
            "leak_rate": rate([i for i in per if items[i]["forbidden_documents"]], "leak"),
            "outcomes": dict(Counter(r["outcome"] for r in per.values())),
            "by_category": {c: round(sum(v) / len(v), 2) for c, v in sorted(by_cat.items())},
            "latency_p50_ms": sorted(r["latency_ms"] for r in rows)[len(rows) // 2] if rows else None,
            "per_item": per}


def main(argv):
    out = None
    if "--json" in argv:
        out, argv = argv[argv.index("--json") + 1], argv[:argv.index("--json")]
    results = [score(argv[0], p) for p in argv[1:]]
    cols = ("accuracy", "answer_accuracy", "not_covered_accuracy", "wrong_seal_rate", "incomplete_rate",
            "wrongly_withheld_rate", "language_mismatch_rate", "leak_rate")
    print(f"{'run':30s} " + " ".join(f"{c[:14]:>14s}" for c in cols) + "  p50ms  outcomes")
    for r in results:
        print(f"{r['run'][:30]:30s} " + " ".join(f"{(r[c] if r[c] is not None else float('nan')):>14.3f}" for c in cols)
              + f"  {r['latency_p50_ms']:>5}  {r['outcomes']}")
    if out:
        json.dump(results, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    assert contains("hạn 17 ngày", "17") and not contains("hạn 17 ngày", "7") and contains("tổng 6.000.000 vnd", "6.000.000")
    main(sys.argv[1:])
