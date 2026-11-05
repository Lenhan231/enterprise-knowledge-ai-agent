#!/usr/bin/env python3
"""Score one run_vietstyle_arm.py output; optionally add an LLM judge; compare two scored arms.

  score:   python scripts/agents/score_vietstyle_arm.py score RUN.json [--judge] [--judge-model M]
  compare: python scripts/agents/score_vietstyle_arm.py compare A.scored.json B.scored.json
Deterministic metrics need no network. --judge calls Groq once per scored case and caches by answer hash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
import re
import statistics
import sys
import time
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
QUESTIONS = ROOT / "artifacts/evaluation/vietstyle-heldout-v1/questions.json"
POLICY_MD = ROOT / "artifacts/datasets/vietstyle-operations-vi-v1/VietStyle_Enterprise_Operating_Policy_v1.0_VN.md"
VIETSTYLE = "VietStyle_Enterprise_Operating_Policy"
# Physical PDF pages, per the dataset's evidence_convention (checked on the VN PDF; EN spot-checked at p14/p35/p53).
DEFAULT_JUDGE = "openai/gpt-oss-120b"
APPENDIX_PAGES = {"cover": {1}, "PL-A": {53}, "PL-B": {53}, "PL-C": {53, 54}, "PL-D": {54}}


def refusals():
    from core.prompts.Knowledge import INSUFFICIENT_ANSWER, NO_MATCHING_DOCUMENTS_ANSWER
    from core.rag.claim_verification import VERIFICATION_UNAVAILABLE_ANSWER
    return {INSUFFICIENT_ANSWER: "insufficient", NO_MATCHING_DOCUMENTS_ANSWER: "no_documents",
            VERIFICATION_UNAVAILABLE_ANSWER: "verifier_block"}


def evidence_pages(item):
    return APPENDIX_PAGES[item] if isinstance(item, str) else {item + 2}


def norm(text):
    return " ".join(unicodedata.normalize("NFC", text or "").casefold().split())


def numbers(text):
    return {re.sub(r"[.,]", "", n) for n in re.findall(r"\d[\d.,]*\d|\d", text or "")}


def key_point_hit(point, answer):
    """'a|b' = either; a purely numeric point matches a number in any 1.000/1,000 spelling."""
    for alt in point.split("|"):
        if re.fullmatch(r"[\d.,]+", alt.strip()):
            if re.sub(r"[.,]", "", alt.strip()) in numbers(answer):
                return True
        elif norm(alt) in norm(answer):
            return True
    return False


def contexts_of(row):
    """Ranked contexts as (page, is_vietstyle, cited); E2E only exposes cited evidence."""
    if "contexts" in row:
        return [(c.get("page_number"), VIETSTYLE in (c.get("document_name") or ""), c.get("cited")) for c in row["contexts"]]
    return [((e.get("metadata") or {}).get("page_number"), VIETSTYLE in (e.get("source") or ""), True)
            for e in row.get("evidence") or [] if e.get("source_type") == "document"]


def retrieval_metrics(case, row):
    items = [evidence_pages(item) for item in case["evidence"]]
    ranked = [page if vs else None for page, vs, _ in contexts_of(row)]
    if not items or "contexts" not in row:
        return {}
    first = next((rank for rank, page in enumerate(ranked, 1) if any(page in item for item in items)), None)
    hit = lambda k: [any(page in item for page in ranked[:k]) for item in items]
    relevant = set().union(*items)
    seen, gains = set(), []
    for page in ranked[:10]:  # a page counts once; later chunks of the same page add no gain
        gains.append(page in relevant and page not in seen)
        seen.add(page)
    ideal = sum(1 / math.log2(r + 1) for r in range(1, min(len(items), 10) + 1))
    return {"recall@5": sum(hit(5)) / len(items), "full@5": all(hit(5)), "mrr": 1 / first if first else 0.0,
            "ndcg@10": sum(g / math.log2(r + 1) for r, g in enumerate(gains, 1)) / ideal}


def citation_metrics(case, row):
    cited = [(page, vs) for page, vs, c in contexts_of(row) if c]
    if not cited or not case["evidence"]:
        return {}
    relevant = set().union(*(evidence_pages(item) for item in case["evidence"]))
    good = [vs and page in relevant for page, vs in cited]
    return {"citation_precision": sum(good) / len(good), "citation_any_correct": any(good)}


def score_row(case, row, refusal):
    answer = row.get("answer") or ""
    out = {"id": case["id"], "type": case["type"], "should_abstain": case["should_abstain"]}
    if row.get("skipped") or row.get("error_type"):
        return {**out, "status": row.get("skipped") or "error:" + row["error_type"]}
    out.update(status="ok", refusal=refusal.get(answer.strip()), elapsed_ms=row.get("elapsed_ms"),
               strict_key_points=(sum(key_point_hit(p, answer) for p in case["must_include"]) / len(case["must_include"])
                                  if case["must_include"] else None),
               **retrieval_metrics(case, row), **citation_metrics(case, row))
    contexts = contexts_of(row)
    if case.get("role"):
        out["rbac_leak"] = any(vs for _, vs, _ in contexts)
    if case.get("expect_no_citations"):
        out["no_citation_ok"] = not any(c for _, _, c in contexts)
    return out


def policy_pages():
    """VN text per physical page, so the judge can read the cited/gold pages without the database."""
    pages, current = {}, 1
    for line in POLICY_MD.read_text(encoding="utf-8").splitlines():
        marker = re.match(r"TRANG CHÍNH SÁCH (\d+)\b", line)
        if marker:
            current = int(marker.group(1)) + 2
        elif line.startswith("Phụ lục A") or line.startswith("Phụ lục B"):
            current = 53
        elif line.startswith("Phụ lục D"):
            current = 54
        pages.setdefault(current, []).append(line)
        if line.startswith("Phụ lục C"):
            pages.setdefault(54, []).append(line)  # PL-C spans both appendix pages
    return {page: "\n".join(lines) for page, lines in pages.items()}


JUDGE = """You grade one answer from a Vietnamese enterprise-policy assistant. Reply with JSON only.

Question: {question}
Case type: {type}. The assistant should {abstain}.
Reference answer: {reference}
Key points (must all be conveyed; wording may differ, e.g. translated synonyms): {points}
Policy text of the gold evidence pages:
<<<{gold}>>>
Policy text of the pages the answer cited (empty if none or not from this policy):
<<<{cited}>>>
Assistant answer:
<<<{answer}>>>

Return {{"correctness": "correct"|"partial"|"incorrect", "key_points_covered": [true/false per key point, same order],
"abstained": true if the answer declines or says the information is insufficient,
"faithful": true if every factual claim is supported by the cited pages (false if it states something they do not say; null if nothing was cited),
"reason": "<one short sentence>"}}.
"correct" = conveys the reference's substance with no wrong or invented facts; for abstain cases, "correct" = declines or states the policy has no such information without inventing figures."""


def judge_prompt(case, row, pages):
    gold = "\n---\n".join(pages.get(p, "") for item in case["evidence"] for p in sorted(evidence_pages(item)))
    cited = "\n---\n".join(dict.fromkeys(pages.get(page, "") for page, vs, c in contexts_of(row) if c and vs and page))
    prompt = JUDGE.format(question=case["question"], type=case["type"], reference=case["reference_answer"],
                          abstain="decline / say the policy does not contain this" if case["should_abstain"] else "answer",
                          points=json.dumps(case["must_include"], ensure_ascii=False), gold=gold[:12000],
                          cited=cited[:12000], answer=row.get("answer") or "")
    return prompt


def parse_verdict(raw, case_id):
    verdict = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
    if verdict.get("correctness") not in {"correct", "partial", "incorrect"}:
        raise ValueError(f"Bad judge verdict for {case_id}: {raw[:200]}")
    return verdict


def judge_case(llm, case, row, pages):
    prompt = judge_prompt(case, row, pages)
    from openai import RateLimitError
    for attempt in range(30):  # per-minute limits on every key can repeat many times in one run
        try:
            raw = llm.generate(prompt, max_output_tokens=600)
            break
        except RateLimitError as error:
            # The provider keeps each limited key cooling (a daily-limited one for up to an hour) and raises only
            # when none is free, so wait for any key; stop only when none frees up (cache resumes the run).
            if attempt == 29:
                raise SystemExit(f"Groq limit reached while judging {case['id']}; rerun later to resume") from error
            time.sleep(min(60.0, float(error.response.headers.get("retry-after") or 10)) + 1)
    return parse_verdict(raw, case["id"])


def judged(row):
    return row["status"] == "ok" and "rbac_leak" not in row  # RBAC is scored by rule: correct iff nothing leaked


def digest(answer):
    return hashlib.sha256((answer or "").encode()).hexdigest()


def load(path):
    run = json.loads(path.read_text())
    if run["dataset_sha256"] != hashlib.sha256(QUESTIONS.read_bytes()).hexdigest():
        raise SystemExit(f"{path} was made on another questions.json version")
    return run, {c["id"]: c for c in json.loads(QUESTIONS.read_bytes())["cases"]}


def export(args):
    """One judge prompt per judged row, for an external judge (e.g. a Codex worker) to answer offline."""
    pages, refusal = policy_pages(), refusals()
    with args.output.open("w", encoding="utf-8") as stream:
        for path in args.runs:
            run, cases = load(path)
            for raw in run["results"]:
                if judged(score_row(cases[raw["id"]], raw, refusal)):
                    stream.write(json.dumps({"arm": run["arm"], "id": raw["id"], "answer_sha256": digest(raw.get("answer")),
                                             "prompt": judge_prompt(cases[raw["id"]], raw, pages)}, ensure_ascii=False) + "\n")


def rate(values):
    values = [v for v in values if v is not None]
    return {"n": len(values), "mean": round(sum(values) / len(values), 3)} if values else {"n": 0}


def summarize(rows):
    ok = [r for r in rows if r["status"] == "ok"]
    answerable = [r for r in ok if not r["should_abstain"] and "rbac_leak" not in r]
    abstain = [r for r in ok if r["should_abstain"]]
    judged = [r for r in ok if "judge" in r]
    refused = lambda r: bool(r.get("refusal")) or bool(r.get("judge", {}).get("abstained"))
    summary = {
        "cases": len(rows), "scored": len(ok), "errors": sum(r["status"].startswith("error") for r in rows),
        "skipped": sum(r["status"] not in {"ok"} and not r["status"].startswith("error") for r in rows),
        **{m: rate([r.get(m) for r in answerable]) for m in ("recall@5", "full@5", "mrr", "ndcg@10",
                                                               "citation_precision", "citation_any_correct", "strict_key_points")},
        "false_abstention": rate([refused(r) for r in answerable]),
        "correct_abstention": rate([refused(r) for r in abstain]),
        "verifier_blocks": sum(r.get("refusal") == "verifier_block" for r in ok),
        "rbac_leaks": sum(bool(r.get("rbac_leak")) for r in ok),
        "rbac_cases": sum("rbac_leak" in r for r in ok),
        "no_citation_ok": [r.get("no_citation_ok") for r in ok if "no_citation_ok" in r],
        "elapsed_ms_median": statistics.median(times) if (times := [r["elapsed_ms"] for r in ok if r.get("elapsed_ms") is not None]) else None,
    }
    if judged:
        verdicts = [r["judge"] for r in judged]
        summary["judge"] = {
            "n": len(judged), "correct": rate([v["correctness"] == "correct" for v in verdicts]),
            "correct_or_partial": rate([v["correctness"] != "incorrect" for v in verdicts]),
            "key_point_coverage": rate([sum(v["key_points_covered"]) / len(v["key_points_covered"])
                                        for v in verdicts if v.get("key_points_covered")]),
            "faithful": rate([v["faithful"] for v in verdicts if v.get("faithful") is not None]),
            "by_type": {t: rate([r["judge"]["correctness"] == "correct" for r in judged if r["type"] == t])
                        for t in sorted({r["type"] for r in judged})},
        }
    return summary


def score(args):
    run, cases = load(args.run)
    refusal = refusals()
    # Each judge gets its own scored file so arms are only ever compared under the same judge.
    out_path = args.run.with_suffix(".scored.json" if args.judge_model == DEFAULT_JUDGE else
                                    f".scored.{re.sub(r'[^a-z0-9]+', '-', args.judge_model.lower())}.json")
    cache = {r["id"]: r for r in json.loads(out_path.read_text())["rows"]} if out_path.exists() else {}
    rows = [score_row(cases[row["id"]], row, refusal) for row in run["results"]]
    if args.verdicts:
        verdicts = {}
        for line in args.verdicts.read_text(encoding="utf-8").splitlines():
            if line.strip():
                item = json.loads(line)
                verdicts[(item["arm"], item["id"])] = item
        for row, raw in zip(rows, run["results"]):
            item = verdicts.get((run["arm"], row["id"]))
            if not judged(row):
                continue
            if not item or item["answer_sha256"] != digest(raw.get("answer")):
                row["judge_error"] = "no verdict for this answer"
                continue
            try:
                row.update(judge=parse_verdict(json.dumps(item["verdict"]), row["id"]),
                           answer_sha256=item["answer_sha256"], judge_model=args.judge_model)
            except ValueError as error:
                row["judge_error"] = str(error)[:300]
    elif args.judge:
        from core.llm.groq_provider import GroqProvider
        llm, pages = GroqProvider(model=args.judge_model), policy_pages()
        for row, raw in zip(rows, run["results"]):
            if not judged(row):
                continue
            answer_sha256 = digest(raw.get("answer"))
            old = cache.get(row["id"], {})
            if old.get("judge") and old.get("answer_sha256") == answer_sha256 and old.get("judge_model") == args.judge_model:
                row.update(judge=old["judge"], answer_sha256=answer_sha256, judge_model=args.judge_model)
                continue
            try:
                row.update(judge=judge_case(llm, cases[row["id"]], raw, pages), answer_sha256=answer_sha256,
                           judge_model=args.judge_model)
            except ValueError as error:  # a malformed verdict is reported, not guessed
                row["judge_error"] = str(error)[:300]
            print(row["id"], row.get("judge", {}).get("correctness", row.get("judge_error")), flush=True)
            out_path.write_text(json.dumps({"run": str(args.run), "arm": run["arm"], "rows": rows},
                                           ensure_ascii=False, indent=1) + "\n")
    report = {"run": str(args.run), "arm": run["arm"], "configuration": run["configuration"],
              "summary": summarize(rows), "rows": rows}
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=1))


def compare(args):
    a, b = (json.loads(p.read_text()) for p in (args.a, args.b))
    correct = lambda r: r.get("status") == "ok" and r.get("judge", {}).get("correctness") == "correct"
    rows_b = {r["id"]: r for r in b["rows"]}
    pairs = [(correct(r), correct(rows_b[r["id"]])) for r in a["rows"]
             if r["id"] in rows_b and "judge" in r and "judge" in rows_b[r["id"]]]
    if not pairs:
        raise SystemExit("No case is judged in both arms")
    only_a, only_b = sum(x and not y for x, y in pairs), sum(y and not x for x, y in pairs)
    n = only_a + only_b
    # Exact two-sided McNemar: binomial test on the discordant pairs.
    p = min(1.0, 2 * sum(math.comb(n, k) for k in range(min(only_a, only_b) + 1)) / 2 ** n) if n else 1.0
    randomizer, diffs = random.Random(20261105), []
    for _ in range(10000):
        sample = [randomizer.choice(pairs) for _ in pairs]
        diffs.append(sum(y - x for x, y in sample) / len(sample))
    diffs.sort()
    print(json.dumps({"a": a["arm"], "b": b["arm"], "paired_cases": len(pairs),
                      "accuracy_a": round(sum(x for x, _ in pairs) / len(pairs), 3),
                      "accuracy_b": round(sum(y for _, y in pairs) / len(pairs), 3),
                      "only_a_correct": only_a, "only_b_correct": only_b, "mcnemar_exact_p": round(p, 4),
                      "b_minus_a_95ci": [round(diffs[249], 3), round(diffs[9749], 3)]}, indent=1))


def main():
    global QUESTIONS
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    s = sub.add_parser("score")
    s.add_argument("run", type=Path)
    s.add_argument("--judge", action="store_true")
    s.add_argument("--judge-model", default=DEFAULT_JUDGE, help="with --verdicts, the external judge's name, e.g. codex")
    s.add_argument("--questions", type=Path, default=QUESTIONS, help="dataset the run used (default: dev set)")
    s.add_argument("--verdicts", type=Path, help="JSONL verdicts from an external judge for prompts made by 'export'")
    e = sub.add_parser("export")
    e.add_argument("runs", type=Path, nargs="+")
    e.add_argument("--output", type=Path, required=True)
    e.add_argument("--questions", type=Path, default=QUESTIONS)
    c = sub.add_parser("compare")
    c.add_argument("a", type=Path)
    c.add_argument("b", type=Path)
    args = parser.parse_args()
    QUESTIONS = getattr(args, "questions", QUESTIONS)
    {"score": score, "compare": compare, "export": export}[args.command](args)


if __name__ == "__main__":
    main()
