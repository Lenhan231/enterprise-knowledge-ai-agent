"""Grade pooled candidate passages with an LLM judge (judge job 2): one Groq call per item, strict JSON, resumable.

  GROQ_API_KEY=... python evaluation/v3/judge_pool.py <pool.json> <out.jsonl> [item ids...]

Grades: 2 = the passage alone answers, 1 = supports the answer, 0 = not useful. A response is accepted only when it
labels every candidate exactly once; otherwise the item is retried (2 retries) and then recorded as an error.
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))
from core.llm.groq_provider import GroqProvider  # noqa: E402
import time  # noqa: E402
from openai import BadRequestError, RateLimitError  # noqa: E402

MODEL = "openai/gpt-oss-120b"
SCHEMA = {
    "description": "You are a strict relevance judge for a policy question-answering evaluation. Return only JSON matching the schema.",
    "type": "object", "additionalProperties": False, "required": ["labels", "item_problem"],
    "properties": {
        "labels": {"type": "array", "items": {
            "type": "object", "additionalProperties": False, "required": ["p", "grade", "why"],
            "properties": {"p": {"type": "string"}, "grade": {"type": "integer", "enum": [0, 1, 2]}, "why": {"type": "string"}}}},
        "item_problem": {"type": "string"},
    },
}
PROMPT = """Judge each candidate passage for the question below. The company policy exists in Vietnamese and English translations; judge either language the same way.

Grades:
2 = the passage ALONE states the fact(s) needed to answer the question correctly.
1 = the passage supports the answer (states part of it, a necessary condition, or a rule the answer relies on) but is not enough alone.
0 = not useful: same topic but a different rule, introductions, contents, generic text, or unrelated. Sharing keywords or a section title is NOT relevance.
Judge only from the passage text. Expected outcome "not_covered" means the documents should NOT answer the question: grade honestly, and if any passage does answer it, explain in item_problem.
Give "why" in at most 12 words (empty string for grade 0). Label every passage P1..P{n} exactly once. item_problem: empty unless the passages show the reference answer or expected outcome is wrong.

Question: {question}
{history}Expected outcome: {outcome}
Reference answer: {reference}

Candidate passages:
{passages}"""


def prompt_for(item):
    history = "".join(f"Earlier turn - Q: {t['question']} A: {t['answer']}\n" for t in item["history"])
    passages = "\n\n".join(f"P{i} [{c['document']} #{c['chunk_index']}]\n{c['text'][:1500]}" for i, c in enumerate(item["candidates"], 1))
    return PROMPT.format(question=item["question"], history=history, outcome=item["expected_outcome"],
                         reference=item["reference_answer"], passages=passages, n=len(item["candidates"]))


def judge(llm, item):
    n = len(item["candidates"])
    attempt = 0
    while attempt < 3:
        try:
            raw = llm.generate(prompt_for(item), max_output_tokens=4000, response_schema=SCHEMA)
            data = json.loads(raw)
            for label in data["labels"]:
                label["p"] = int(re.fullmatch(r"P?(\d+)", label["p"].strip()).group(1))
            ps = sorted(label["p"] for label in data["labels"])
            if ps != list(range(1, n + 1)):
                raise ValueError(f"labels cover {ps}, expected 1..{n}")
            by_p = {label["p"]: label for label in data["labels"]}
            labels = [{"document": c["document"], "chunk_index": c["chunk_index"], "grade": by_p[i]["grade"], "why": by_p[i]["why"]}
                      for i, c in enumerate(item["candidates"], 1)]
            return {"id": item["id"], "set": item["set"], "labels": labels, "item_problem": data["item_problem"],
                    "model": MODEL, "attempts": attempt + 1}
        except RateLimitError as error:
            # Every key is cooling down: wait as Groq asks; a quota wait is not a failed attempt.
            wait = re.search(r"try again in (?:(\d+)m)?([\d.]+)s", str(error))
            time.sleep(min(600, (int(wait.group(1) or 0) * 60 + float(wait.group(2)) + 1) if wait else 30))
            continue
        except (BadRequestError, ValueError, KeyError, TypeError, AttributeError) as error:
            last = str(error)
        attempt += 1
    return {"id": item["id"], "set": item["set"], "error": last, "model": MODEL}


def main(pool_path, out_path, *only):
    pool = json.load(open(pool_path, encoding="utf-8"))
    done = set()
    if Path(out_path).exists():
        done = {json.loads(line)["id"] for line in open(out_path, encoding="utf-8") if "error" not in json.loads(line)}
    llm = GroqProvider(model=MODEL)
    with open(out_path, "a", encoding="utf-8") as out:
        for item in pool:
            if item["id"] in done or (only and item["id"] not in only) or not item["candidates"]:
                continue
            result = judge(llm, item)
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            print(item["id"], "error: " + result["error"] if "error" in result else
                  f"{sum(1 for l in result['labels'] if l['grade'] == 2)}x2 {sum(1 for l in result['labels'] if l['grade'] == 1)}x1 / {len(result['labels'])}",
                  flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
