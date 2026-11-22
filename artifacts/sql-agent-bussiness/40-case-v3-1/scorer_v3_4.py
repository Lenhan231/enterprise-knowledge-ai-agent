"""Offline v3.4.0 rescore with narrow, recorded result-format equivalence."""

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
VERSION = "3.4.0"
_DATE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])-01")
_UTC_MONTH_START = re.compile(r"(\d{4}-(?:0[1-9]|1[0-2])-01)T00:00:00(?:\.0+)?(?:\+00:00|Z)")


def _read(path):
    return json.loads(Path(path).read_bytes())


def _sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def query_sha256(observation):
    query = {name: observation.get(name) for name in ("sql", "parameters")}
    return hashlib.sha256(json.dumps(query, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode()).hexdigest()


def normalize_month_starts(case, reference_rows, observation):
    if ("month" not in case["output_contract"]["columns"]
            or not reference_rows or not isinstance(observation.get("rows"), list)):
        return observation
    dates = [row.get("month") for row in reference_rows]
    if not all(isinstance(value, str) and _DATE.fullmatch(value) for value in dates):
        return observation

    def normalize(value):
        match = _UTC_MONTH_START.fullmatch(value) if isinstance(value, str) else None
        return match[1] if match else value

    rows = [{key: normalize(value) if key.casefold() == "month" else value
             for key, value in row.items()} if isinstance(row, dict) else row
            for row in observation["rows"]]
    return {**observation, "rows": rows}


def with_reviewed_aliases(case, observation, review, *, semantic_pass):
    if (not semantic_pass or not review or review.get("case_id") != case["id"]
            or review.get("query_sha256") != query_sha256(observation)):
        return case
    mapping = review["aliases"]
    required = case["output_contract"]["columns"]
    observed = observation["columns"]
    if (not review.get("evidence") or len(set(mapping.values())) != len(mapping)
            or any(source not in observed or source.casefold() in {x.casefold() for x in required}
                   or target not in required for source, target in mapping.items())):
        raise ValueError(f"Invalid reviewed aliases for {case['id']}")
    aliases = {key: list(values) for key, values in case.get("column_aliases", {}).items()}
    for source, target in mapping.items():
        if any(source.casefold() == value.casefold() for values in aliases.values() for value in values):
            raise ValueError(f"Alias {source} is already defined for {case['id']}")
        aliases.setdefault(target, []).append(source)
    return {**case, "column_aliases": aliases}


def rescore(cases, reference, experiment, alias_reviews):
    # Isolated module instance preserves the pinned v3.3 scorer and its audit
    # linkage. Only the inputs to its business-result comparator are adapted.
    spec = importlib.util.spec_from_file_location("sql_benchmark_v3_3_offline", HERE / "scorer_v3_1.py")
    scorer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(scorer)
    strict = scorer.score(cases, reference, experiment)
    compare = scorer.compare_business_results
    reviews = {row["case_id"]: row for row in alias_reviews}
    if len(reviews) != len(alias_reviews):
        raise ValueError("Duplicate reviewed alias cases")
    applied = {}

    def compare_normalized(case, rows, observation, *, reference_sql=None):
        case_id = case["id"]
        semantic_pass = strict["semantic_audits"][case_id]["decision"] == "PASS"
        adjusted = with_reviewed_aliases(case, observation, reviews.get(case_id), semantic_pass=semantic_pass)
        normalized = normalize_month_starts(case, rows, observation)
        if adjusted != case or normalized != observation:
            applied[case_id] = {
                "normalized_month_starts": normalized != observation,
                "reviewed_aliases": reviews[case_id]["aliases"] if adjusted != case else {},
            }
        result = compare(adjusted, rows, normalized, reference_sql=reference_sql)
        official = strict["case_comparisons"][case_id]
        for name in ("strict_schema_match", "strict_rows_match"):
            result[name] = official[name]
        return result

    scorer.compare_business_results = compare_normalized
    normalized = scorer.score(cases, reference, experiment)
    if any(case_id not in applied or not applied[case_id]["reviewed_aliases"] for case_id in reviews):
        raise ValueError("A reviewed alias did not match the exact audited observation")
    normalized.update(
        scorer_version=VERSION,
        format_version="sql-agent-business-offline-format-rescore.v3.4",
        official_v3_3_metrics=strict["metrics"],
        formatting_changes=applied,
    )
    return normalized


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--alias-reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw_path = args.run_dir / "data.json"
    raw = _read(raw_path)
    review_doc = _read(args.alias_reviews)
    if review_doc.get("raw_observations_sha256") != _sha(raw_path):
        raise ValueError("Alias reviews do not match the saved raw run")
    inputs = {
        "observations": raw_path,
        "cases": HERE / "cases_v3_1_draft.json",
        "reference": HERE / "gold_results_v3_1_provisional.json",
        "semantic_audits": args.run_dir / "semantic_audits.json",
        "output_safety_audits": args.run_dir / "output_safety_audits.json",
        "alias_reviews": args.alias_reviews,
        "scorer_v3_3": HERE / "scorer_v3_1.py",
        "scorer_v3_4": Path(__file__),
    }
    cases = _read(inputs["cases"])
    reference = _read(inputs["reference"])
    if (raw.get("case_set_sha256") != reference.get("case_set_sha256")
            or raw["manifest"]["dataset_fingerprint_sha256"] != reference["database_fingerprint_sha256"]):
        raise ValueError("Saved run does not match the frozen cohort and database snapshot")
    for name, key in (("semantic_audits", "independent_semantic_audits"),
                      ("output_safety_audits", "additional_output_safety_audits")):
        raw[key] = _read(inputs[name])[key]
    result = rescore(cases, reference, raw, review_doc["reviews"])
    result["scoring_input_hashes"] = {name: _sha(path) for name, path in inputs.items()}
    with args.output.open("x", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
        handle.write("\n")


if __name__ == "__main__":
    main()
