#!/usr/bin/env python3
"""Validate evaluation-only evidence labels against frozen source text; no models/services."""
import argparse
import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOLDER = ROOT / "artifacts/evaluation/vietstyle-bilingual-20261019/evidence-v1"

def require(ok, message):
    if not ok:
        raise ValueError(message)

def digest(raw):
    return hashlib.sha256(raw).hexdigest()

def validate(data):
    sources, questions = {}, {}
    for language in ("vi", "en"):
        for kind, store in [("sources", sources), ("question_sources", questions)]:
            meta = data[kind][language]
            raw = (ROOT / meta["path"]).read_bytes()
            require(digest(raw) == meta["sha256"], f"Changed {language} {kind}; version or reanchor labels")
            if kind == "sources":
                store[language] = {}
                for line in raw.decode("utf-8").splitlines():
                    row = json.loads(line)
                    index = row.get("parser_chunk_index", row.get("chunk_index"))
                    store[language][row["document_id"], index] = row
            else:
                store[language] = {q["id"]: q for q in json.loads(raw)["cases"]}
    provenance = data["translation_provenance"]
    require(digest((ROOT / provenance["english_build_manifest_path"]).read_bytes()) == provenance["english_build_manifest_sha256"], "English translation provenance changed")
    require(data["rules"]["evaluation_only"] and data["rules"]["never_index_labels_questions_or_answers"], "Labels must remain evaluation-only")
    spans = data["spans"]
    for sid, span in spans.items():
        require(sid == span["id"], f"Bad span ID {sid}")
        row = sources[span["language"]].get((span["document_id"], span["source_parser_index"]))
        require(row is not None, f"Missing source {sid}")
        text = row["content"]
        require(digest(text.encode()) == span["source_content_sha256"], f"Changed source passage {sid}")
        name = row.get("document_name", row["metadata"].get("filename"))
        require(name == span["document_name"], f"Wrong document {sid}")
        a, b = span["start_char"], span["end_char"]
        require(isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(text), f"Bad offsets {sid}")
        require(text[a:b] == span["quote"] and bool(span["quote"].strip()), f"Quotation mismatch {sid}")
        for key, value in span["location"].items():
            require(row["metadata"].get(key) == value, f"Wrong location {sid}: {key}")
    used, statuses, required_statuses, ids = set(), Counter(), Counter(), set()
    for question in data["intents"]:
        qid = question["id"]
        require(qid not in ids, "Duplicate intent")
        ids.add(qid)
        require(bool(question["requirements"]), f"No requirements: {qid}")
        for language in ("vi", "en"):
            original = questions[language][qid]
            require(question["question"][language] == original["question"], f"Question changed: {qid}/{language}")
            require(question["reference_answer"][language] == original["reference_answer"], f"Reference changed: {qid}/{language}")
        component_ids = set()
        for component in question["requirements"]:
            require(component["id"] not in component_ids, f"Duplicate requirement {qid}")
            component_ids.add(component["id"])
            require(component["description_vi"] and "?" not in component["description_vi"], f"Unreadable description {component['id']}")
            statuses[component["status"]] += 1
            if component["required"]:
                required_statuses[component["status"]] += 1
            for language in ("vi", "en"):
                alternatives = component["evidence_by_language"][language]["alternatives"]
                require(bool(alternatives), f"Unlabelled language {component['id']}/{language}")
                for option in alternatives:
                    require(bool(option["all_of"]), f"Empty evidence bundle {component['id']}")
                    for sid in option["all_of"]:
                        require(sid in spans and spans[sid]["language"] == language, f"Wrong-language/missing evidence {sid}")
                        used.add(sid)
                for sid in component.get("conflicting_source_spans", {}).get(language, []):
                    require(sid in spans and spans[sid]["language"] == language, f"Bad conflict source {sid}")
                    used.add(sid)
            if component["status"] == "needs_policy_resolution":
                require(component.get("review_note") and set(component.get("conflicting_source_spans", {})) == {"vi", "en"}, "Policy conflict must include both source versions")
        ready = all(x["status"] == "ready" for x in question["requirements"] if x["required"])
        require(question["full_intent_ready"] == ready, f"Readiness mismatch {qid}")
    require(ids == {f"Q{i:02d}" for i in range(1, 21)}, "Expected all 20 intents")
    require(used == set(spans), "Unused or unregistered evidence spans")
    # The numeric scenario is supplied by the question; formulas/defaults require source evidence.
    by_id = {q["id"]: q for q in data["intents"]}
    for derivation in by_id["Q09"]["derivations"]:
        n = derivation["inputs_from_question"]["daily_demand"]
        inputs = derivation["inputs_from_evidence"]
        result = n * (inputs["lead_time"] + inputs["safety_days"] + inputs.get("review_period", 0))
        require(result == derivation["expected_result"], "Q09 arithmetic mismatch")
    derivation = by_id["Q10"]["derivations"][0]
    x = derivation["inputs_from_question"]
    require(x["on_hand"] + x["open_po"] - x["backorder"] == derivation["expected_result"], "Q10 arithmetic mismatch")
    return {"intents": len(ids), "language_versions": 40, "requirements": sum(statuses.values()),
            "required_status_counts": dict(required_statuses), "all_status_counts": dict(statuses),
            "source_spans": len(spans), "spans_by_language": dict(Counter(x["language"] for x in spans.values())),
            "fully_ready_intents": sum(q["full_intent_ready"] for q in data["intents"]),
            "not_fully_ready": [q["id"] for q in data["intents"] if not q["full_intent_ready"]],
            "checks": "Source/question/provenance SHA256, exact Unicode offsets/quotes, locations, both languages, references, required/optional/conflict status, complete source references and scenario arithmetic.",
            "limits": "Mechanical validation is not independent semantic certification. Alternatives remain non-exhaustive; no retrieval, generation or model quality has been evaluated."}

def review_markdown(data):
    spans = data["spans"]
    out = [f"# {data['dataset_id']} — human-readable review", "", "Evaluation-only labels; do not index this file. VI and EN quotes below are exact frozen-source excerpts. AND across required ready components; OR across alternatives; all spans in one bundle are required. Q14 role variants need policy resolution; optional context is not required. Full alternatives are in evidence.json.", ""]
    for q in data["intents"]:
        out.extend([f"## {q['id']}", "", q["question"]["vi"], "", q["question"]["en"], ""])
        for requirement in q["requirements"]:
            out.extend([f"### {requirement['id']} — {requirement['description_vi']}", "", f"Status: {requirement['status']}; required: {requirement['required']}.", ""])
            if requirement.get("review_note"):
                out.extend([requirement["review_note"], ""])
            for lang in ("vi", "en"):
                options = requirement["evidence_by_language"][lang]["alternatives"]
                out.extend([f"**{lang.upper()}** — {len(options)} alternative bundle(s). First bundle:", ""])
                for sid in options[0]["all_of"]:
                    span = spans[sid]
                    out.extend([f"`{sid}` — {span['document_name']}, parser index {span['source_parser_index']}, chars [{span['start_char']}, {span['end_char']}).", "", "> " + span["quote"].replace("\n", "\n> "), ""])
                for sid in requirement.get("conflicting_source_spans", {}).get(lang, []):
                    span = spans[sid]
                    out.extend([f"Conflicting role list: `{span['document_name']}` / `{sid}`", "", "> " + span["quote"].replace("\n", "\n> "), ""])
        for derivation in q.get("derivations", []):
            out.extend([f"Calculation (question inputs + source formulas): `{derivation['expression']} = {derivation['expected_result']}`.", ""])
        out.extend(q["notes"] + [""])
    return "\n".join(out) + "\n"

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true", help="Also prove a tampered quote and wrong-language reference are rejected")
    parser.add_argument("--folder", type=Path, default=FOLDER, help="Versioned label folder; default preserves v1")
    args = parser.parse_args()
    path = args.folder / "evidence.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    summary = validate(data)
    if args.self_check:
        for damage in ("quote", "language"):
            bad = copy.deepcopy(data)
            first = next(iter(bad["spans"].values()))
            if damage == "quote":
                first["quote"] += " NOT IN SOURCE"
            else:
                first["language"] = "en" if first["language"] == "vi" else "vi"
            try:
                validate(bad)
            except ValueError:
                continue
            raise ValueError(f"Validator failed to reject tampered {damage}")
        summary["self_check"] = "Tampered quotation and wrong-language source rejected"
    summary["evidence_json_sha256"] = digest(path.read_bytes())
    (args.folder / "validation.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.folder / "REVIEW.md").write_text(review_markdown(data), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
