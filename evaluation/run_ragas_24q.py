"""Score existing QuocAn benchmark answers with the RAGAS collections API.

Requires: Gemini API access and the configured local embedding model
Environment: GEMINI_API_KEY; optional per-metric RAGAS model names
Optional: evaluation/reference_answers.json mapping Q01..Q24 -> verified answer.
"""
import asyncio
import csv
import json
import os
import re
from pathlib import Path

from openai import AsyncOpenAI
from ragas.llms import llm_factory
from ragas.embeddings.base import embedding_factory
from ragas.metrics.collections import Faithfulness, AnswerRelevancy, ContextPrecision
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
INPUT = ROOT / "artifacts/benchmark/long_hau_2008.json"
REFERENCES = ROOT / "evaluation/reference_answers.json"
OUTPUT = ROOT / "artifacts/benchmark/ragas_scores.csv"

def save_results(records):
    if not records:
        return
    temp = OUTPUT.with_suffix(".csv.tmp")
    with temp.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    temp.replace(OUTPUT)


def load_verified_references():
    if not REFERENCES.exists():
        return {}
    obj = json.loads(REFERENCES.read_text(encoding="utf-8"))
    return {k: str(v).strip() for k, v in obj.items() if str(v).strip()}

async def main():
    data = json.loads(INPUT.read_text(encoding="utf-8"))
    references = load_verified_references()
    if len(data["results"]) != 24:
        raise ValueError("Benchmark artifact is not the expected 24-case dataset")
    gemini_key = os.getenv("GEMINI_API_KEY")
    if not gemini_key:
        raise RuntimeError("GEMINI_API_KEY is required for the RAGAS judge")
    faithfulness_model = os.getenv("RAGAS_FAITHFULNESS_MODEL", "gemini-3.1-flash-lite")
    judge_model = os.getenv("RAGAS_JUDGE_MODEL", "gemini-3.1-flash-lite")
    context_precision_model = os.getenv("RAGAS_CONTEXT_PRECISION_MODEL", "gemini-3.1-flash-lite")
    gemini_client = AsyncOpenAI(
        api_key=gemini_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        timeout=60,
    )
    metric_judges = {
        "faithfulness": llm_factory(faithfulness_model, client=gemini_client, max_tokens=1024),
        "answer_relevancy": llm_factory(judge_model, client=gemini_client, max_tokens=1024),
        "context_precision": llm_factory(context_precision_model, client=gemini_client, max_tokens=1024),
    }
    embeddings = embedding_factory(
        "huggingface",
        model=os.getenv("EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
    )
    metrics = {
        "faithfulness": Faithfulness(llm=metric_judges["faithfulness"]),
        "answer_relevancy": AnswerRelevancy(llm=metric_judges["answer_relevancy"], embeddings=embeddings),
        "context_precision": ContextPrecision(llm=metric_judges["context_precision"]),
    }
    records = []
    if OUTPUT.exists():
        with OUTPUT.open(newline="", encoding="utf-8-sig") as f:
            records = list(csv.DictReader(f))
        records = [r for r in records if r["status"] != "PARTIAL"]
    completed = {(r["question_id"], r["model"]) for r in records}
    for item in data["results"]:
        contexts = [c["content"] for c in item["retrieved_contexts"]]
        reference = references.get(item["id"])
        for name in data["model_names"]:
            if (item["id"], name) in completed:
                continue
            generated = item.get("models", {}).get(name, {})
            answer = generated.get("answer", "").strip()
            row = {
                "question_id": item["id"], "model": name, "question": item["question"],
                "answer": answer, "faithfulness": "", "answer_relevancy": "",
                "context_precision": "", "hallucination_rate": "",
                "status": "NO_RESPONSE" if not answer else "SCORED",
                "error": generated.get("error", ""),
            }
            if not answer:
                records.append(row)
                save_results(records)
                continue
            params = {"user_input": item["question"], "response": answer,
                      "retrieved_contexts": contexts}
            relevancy_params = {"user_input": item["question"], "response": answer}
            requested = [
                ("faithfulness", metrics["faithfulness"], params),
                ("answer_relevancy", metrics["answer_relevancy"], relevancy_params),
            ]
            if reference:
                requested.append(("context_precision", metrics["context_precision"], {
                    "user_input": item["question"],
                    "reference": reference,
                    "retrieved_contexts": contexts,
                }))

            async def score_one(metric_name, metric, arguments):
                for attempt in range(3):
                    try:
                        result = await metric.ascore(**arguments)
                        return metric_name, round(float(result.value), 4), ""
                    except Exception as exc:
                        message = str(exc)
                        if attempt < 2 and ("429" in message or "rate_limit" in message.lower()):
                            retry = re.search(
                                r"(?:try again in|retry in) ([\d.]+)s", message, re.IGNORECASE
                            )
                            await asyncio.sleep(float(retry.group(1)) + 1 if retry else 20)
                            continue
                        return metric_name, "", f"{type(exc).__name__}: {message}"

            for offset in range(0, len(requested), 2):
                results = await asyncio.gather(
                    *(score_one(metric_name, metric, arguments)
                      for metric_name, metric, arguments in requested[offset:offset + 2])
                )
                for metric_name, value, error in results:
                    row[metric_name] = value
                    if error:
                        row["status"] = "PARTIAL"
                        row["error"] += f" {metric_name}: {error}"
            if not reference and row["status"] == "SCORED":
                row["status"] = "NEEDS_REFERENCE"
            # Hallucination rate is a separately audited claim-level metric.
            # Do NOT use 1 - faithfulness as a silently substituted score.
            records.append(row)
            completed.add((item["id"], name))
            save_results(records)
            print(f'{row["question_id"]} / {name}: {row["status"]}', flush=True)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    print(f"Saved {len(records)} rows to {OUTPUT}")

if __name__ == "__main__":
    asyncio.run(main())
