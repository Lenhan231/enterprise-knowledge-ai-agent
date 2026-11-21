"""Run the reviewed one-change mutation catalog against v3.1 contracts."""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ARTIFACTS = HERE.parent
PREPARATION = ARTIFACTS / "40-case-preparation"
V3 = ARTIFACTS / "40-case-v3"
sys.path[:0] = [str(ROOT / "src"), str(ARTIFACTS), str(PREPARATION), str(V3)]

_SPEC = importlib.util.spec_from_file_location("sql_mutation_runner_v3", V3 / "run_mutation_probes_v3.py")
if _SPEC is None or _SPEC.loader is None:
    raise ImportError("Could not load the reviewed read-only mutation executor")
_RUNNER = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_RUNNER)


def _file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_hashes(paths: list[Path]) -> dict[str, str]:
    return {
        str(path.relative_to(ROOT)): _file_sha256(path)
        for path in paths if path.is_file()
    }


async def run(cases_path: Path, gold_sql_path: Path, gold_results_path: Path,
              preflight_path: Path, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError(f"Refusing to overwrite immutable mutation evidence: {output_path}")
    case_doc = json.loads(cases_path.read_text(encoding="utf-8"))
    gold_doc = json.loads(gold_sql_path.read_text(encoding="utf-8"))
    gold_results_doc = json.loads(gold_results_path.read_text(encoding="utf-8"))
    preflight_doc = json.loads(preflight_path.read_text(encoding="utf-8"))
    result = await _RUNNER.execute_probes(
        case_doc, gold_doc, gold_results_doc, preflight_doc,
        preflight_path, gold_results_path,
    )
    result.update({
        "format_version": "sql-40-case-mutation-results.v3.1",
        "protocol_version": "3.1.0",
        "run_id": "mutation-v3-1-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"),
        "case_set_file_sha256": _file_sha256(cases_path),
        "gold_sql_file_sha256": _file_sha256(gold_sql_path),
        "gold_results_rerun_file_sha256": _file_sha256(gold_results_path),
        "provisional_gold_results_file_sha256": _file_sha256(HERE / "gold_results_v3_1_provisional.json"),
        "preflight_file_sha256": _file_sha256(preflight_path),
        "source_hashes_v3_1": _source_hashes([
            cases_path, gold_sql_path, HERE / "gold_results_v3_1_provisional.json",
            gold_results_path, preflight_path,
            HERE / "semantic_audit_v3_1.py", HERE / "scorer_v3_1.py",
            HERE / "generate_gold_results_v3_1.py", HERE / "run_mutation_probes_v3_1.py",
            V3 / "mutation_probes_v3.py", V3 / "run_mutation_probes_v3.py",
            V3 / "scorer_v3.py", V3 / "followup_adapter.py",
            PREPARATION / "dataset_validator.py", PREPARATION / "preflight_40.py",
            ARTIFACTS / "preflight.py",
            ROOT / "src/core/agents/sql/metric_validation.py",
            ROOT / "src/core/agents/sql/sql_validation.py",
            ROOT / "src/core/agents/sql/join_validation.py",
            ROOT / "src/core/database/commerce_repository.py",
        ]),
        "database_write_attempts": 0,
        "sql_agent_generation_calls": 0,
        "heldout_agent_executed": False,
    })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(result, ensure_ascii=False, indent=2,
                                default=_RUNNER._json_value) + "\n")
    return result


async def _main(args):
    result = await run(Path(args.cases), Path(args.gold_sql), Path(args.gold_results),
                       Path(args.preflight), Path(args.output))
    print(json.dumps({
        "status": result["status"],
        "mutations_attempted": result["mutations_attempted"],
        "failures": result["failures"],
        "result_based_mutation_detection": result["result_based_mutation_detection"],
        "observationally_equivalent": result["observationally_equivalent"],
        "validator_detection": result["validator_detection"],
        "fingerprint": result["database_fingerprint_sha256"],
        "read_only_role": result["database_role_read_only"],
        "heldout_agent_executed": result["heldout_agent_executed"],
        "output": args.output,
    }, ensure_ascii=False, indent=2))
    if result["status"] != "COMPLETE_NOT_APPROVED":
        raise SystemExit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", default=str(HERE / "cases_v3_1_draft.json"))
    parser.add_argument("--gold-sql", default=str(HERE / "gold_sql_v3_1_draft.json"))
    parser.add_argument("--gold-results", required=True)
    parser.add_argument("--preflight", required=True)
    parser.add_argument("--output", required=True)
    asyncio.run(_main(parser.parse_args()))
