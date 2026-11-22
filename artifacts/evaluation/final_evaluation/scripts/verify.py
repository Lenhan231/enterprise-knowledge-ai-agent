"""Verify the package and optionally repeat the deterministic replay."""
import argparse
import asyncio
from importlib.metadata import version
import json
import platform
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from openai import RateLimitError

import judge
import replay
from freeze import PACKAGE, ROOT, digest, write
from core.llm.groq_provider import GroqProvider


def failover():
    provider = GroqProvider(api_keys=["fake-a", "fake-b", "fake-c"], model="qwen/qwen3.8-27b")
    response = httpx.Response(429, headers={"retry-after": "60"}, request=httpx.Request("POST", "https://groq.test"))
    throttled = RateLimitError("fixture throttle", response=response, body=None)
    success = SimpleNamespace(output_text="OK", usage=None)
    with patch.object(provider, "_create", side_effect=[throttled, throttled, success]) as call:
        assert provider.generate("Fixture") == "OK"
    assert [item.args[0] for item in call.call_args_list] == [0, 1, 2]
    return "pass"


def scoring_view():
    return {group: [{key: val for key, val in row.items() if key != "latency_ms"} for row in replay.load(f"results/{group}/cases.json")]
            for group in ("dashboard", "report")}


def main(repeat):
    replay.verify_inputs()
    views = scoring_view()
    assert len(views["dashboard"]) == 20 and len(views["report"]) == 40
    by_id = {row["id"]: row for rows in views.values() for row in rows}
    for group, rows in views.items():
        for row in rows:
            assert (ROOT / "results" / group / (row["id"] + ".raw.json")).is_file()
            assert row["status"] in {"pass", "fail", "blocked"}
    for id, extension in (("R37", "md"), ("R38", "docx"), ("R40", "json")):
        assert (ROOT / "results/report" / f"{id}.{extension}").stat().st_size > 0
    judgments = judge.load("judge/judgments.json")
    rubric = judge.load("judge/rubric.json")
    eligible = {id for id, row in by_id.items() if row["semantic"]}
    assert {row["id"] for row in judgments["records"]} == eligible
    for row in judgments["records"]:
        case = by_id[row["id"]]
        prompt = judge.prompt(rubric, case["judge_input"], case["semantic"])
        assert digest(json.dumps(judgments["settings"], sort_keys=True).encode() + prompt.encode()) == row["input_sha256"]
        if row["status"] == "scored":
            assert judge.validate(row["raw"], case["semantic"], {src["id"] for src in case["judge_input"]["evidence"]}) == row["scores"]
    assert judge.validate('{"scores":{"d":{"score":2,"reasoning":"Supported","evidence_ids":["E"]}}}', ["d"], {"E"})
    try:
        judge.validate('{"scores":{"d":{"score":true,"reasoning":"Invalid","evidence_ids":["E"]}}}', ["d"], {"E"})
    except ValueError:
        pass
    else:
        raise AssertionError("Judgment schema accepted a boolean score")
    if repeat:
        asyncio.run(replay.main())
        assert scoring_view() == views, "Repeated replay changed a deterministic observation or judge input"
    write("config/verification.json", {
        "provenance": "pass", "judgment_schema": "pass", "gold_replay_repeated": repeat,
        "groq_failover_simulated": failover(), "python": platform.python_version(), "platform": platform.system(),
        "packages": {name: version(name) for name in ("openai", "pydantic", "sqlglot", "python-docx", "fastapi")},
        "harness_sha256": {path.name: digest(path.read_bytes()) for path in (PACKAGE / "scripts").glob("*.py")},
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--repeat", action="store_true")
    main(parser.parse_args().repeat)
