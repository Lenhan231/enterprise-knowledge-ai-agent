"""RAGAS Faithfulness, Answer Relevancy and Context Precision for v3 answer runs, judged by Groq gpt-oss-120b.

Run with the isolated venv (artifacts/local/eval-v3/ragas-venv, ragas 0.4.3):
  ragas-venv/bin/python evaluation/v3/ragas_eval.py <dev|test> <answers.jsonl> <out.jsonl>

Only items whose answer is shown (sealed / unverified / answered) and expected to be answered are judged; refusals have
no faithfulness. Hallucination = faithfulness < 1 (at least one claim not supported by the retrieved contexts).
The judge model is not the answer model (qwen) and not Claude. Resumable; keys rotate per item.
"""
import asyncio
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
JUDGE = "openai/gpt-oss-120b"


def keys():
    env = Path(os.getenv("EVAL_PROD_ENV", Path.home() / "projects/ekai-prod/.env")).read_text().splitlines()
    return [line.split("=", 1)[1].strip() for line in env if line.startswith("GROQ_API_KEY") and "=" in line and line.split("=", 1)[1].strip()]


def metrics_for(key, embeddings):
    from openai import AsyncOpenAI
    from ragas.llms import llm_factory
    from ragas.metrics.collections import AnswerRelevancy, ContextPrecision, Faithfulness
    client = AsyncOpenAI(api_key=key, base_url="https://api.groq.com/openai/v1", max_retries=6)
    llm = llm_factory(JUDGE, client=client, max_tokens=4000)
    return Faithfulness(llm=llm), AnswerRelevancy(llm=llm, embeddings=embeddings), ContextPrecision(llm=llm)


async def main(set_name, answers_path, out_path):
    from ragas.embeddings.base import embedding_factory
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from score_answers import SHOWN, outcome
    items = {i["id"]: i for i in json.load(open(ROOT / f"artifacts/evaluation/vietstyle-v3/{set_name}-v3.json", encoding="utf-8"))["items"]}
    embeddings = embedding_factory("huggingface", model="intfloat/multilingual-e5-base")
    pool = keys()
    done = {json.loads(l)["id"] for l in open(out_path, encoding="utf-8")} if Path(out_path).exists() else set()
    with open(out_path, "a", encoding="utf-8") as out:
        for n, line in enumerate(open(answers_path, encoding="utf-8")):
            row = json.loads(line)
            item = items.get(row.get("id"))
            if not item or row["id"] in done or "error" in row or item["expected_outcome"] != "answer" or outcome(row) not in SHOWN:
                continue
            faithfulness, relevancy, precision = metrics_for(pool[n % len(pool)], embeddings)
            contexts = [c["content"] for c in row["contexts"]]
            question = item["question"] if not item["history"] else (
                " ".join(f"(Trước đó: {t['question']})" for t in item["history"]) + " " + item["question"])
            result = {"id": row["id"]}
            for name, call in (("faithfulness", lambda: faithfulness.ascore(user_input=question, response=row["answer"], retrieved_contexts=contexts)),
                               ("answer_relevancy", lambda: relevancy.ascore(user_input=question, response=row["answer"])),
                               ("context_precision", lambda: precision.ascore(user_input=question, reference=item["reference_answer"], retrieved_contexts=contexts))):
                try:
                    result[name] = float((await call()).value)
                except Exception as error:  # a judge failure is recorded, never scored as 0
                    result[name] = None
                    result.setdefault("errors", {})[name] = f"{type(error).__name__}: {str(error)[:160]}"
            result["hallucination"] = None if result["faithfulness"] is None else result["faithfulness"] < 1.0
            out.write(json.dumps(result, ensure_ascii=False) + "\n")
            out.flush()
            print(row["id"], {k: (round(v, 2) if isinstance(v, float) else v) for k, v in result.items() if k != "id"}, flush=True)
            time.sleep(float(os.getenv("EVAL_PACE_SECONDS", "2")))


if __name__ == "__main__":
    asyncio.run(main(*sys.argv[1:4]))
