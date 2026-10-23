"""Paired ablation: original BGE pairs versus source-context for short passages."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import zipfile
from time import perf_counter

import numpy as np
import evaluate_embedding_candidates as candidate
import evaluate_vietstyle_reranker as previous
import validate_vietstyle_evidence as validator
from compare_vietstyle_evidence import check, digest

ROOT = candidate.ROOT
RELATIVE = Path("artifacts/evaluation/vietstyle-bilingual-20261019")
OUT = ROOT / RELATIVE / "dense-evidence-benchmark-v1/source-context-cpu-v1"
SHORT_CHARS = 800


def render(rows, index):
    """Only source metadata; no question, labels, scores or answer text."""
    row = rows[index]
    text = row["content"]
    if len(text) > SHORT_CHARS:
        return text
    metadata = row["metadata"]
    section = metadata.get("section_title")
    if not section:
        earlier = [(i, r) for i, r in enumerate(rows)
                   if r["document_id"] == row["document_id"]
                   and r["language"] == row["language"]
                   and r["chunk_index"] < row["chunk_index"]
                   and r["metadata"].get("page_number") == metadata.get("page_number")
                   and r["metadata"].get("sheet_name") == metadata.get("sheet_name")
                   and r["metadata"].get("slide_number") == metadata.get("slide_number")
                   and r["metadata"].get("section_title")
                   and set(r["allowed_roles"] or []) == set(row["allowed_roles"] or [])]
        if earlier:
            _, parent = max(earlier, key=lambda item: item[1]["chunk_index"])
            section = parent["metadata"]["section_title"]
    lines = [f"Source document: {row['document_name']}"]
    if section:
        lines.append(f"Source section: {section}")
    if metadata.get("table_title"):
        lines.append(f"Source table: {metadata['table_title']}")
    return "\n".join(lines) + "\nPassage:\n" + text


def render_parent(rows, index, include_metadata=True):
    """Add one preceding source passage using location/ACL metadata only."""
    row = rows[index]
    base = render(rows, index) if include_metadata else row["content"]
    if len(row["content"]) > SHORT_CHARS:
        return base
    metadata = row["metadata"]
    for prior in rows:
        if (prior["document_id"] != row["document_id"] or prior["language"] != row["language"]
                or prior["chunk_index"] != row["chunk_index"] - 1
                or prior["metadata"]["source_parser_index"] != metadata["source_parser_index"] - 1
                or set(prior["allowed_roles"] or []) != set(row["allowed_roles"] or [])):
            continue
        if any(prior["metadata"].get(k) != metadata.get(k) for k in ("page_number", "sheet_name", "slide_number")):
            continue
        left, right = prior["metadata"].get("section_title"), metadata.get("section_title")
        if not any(metadata.get(k) is not None for k in ("page_number", "sheet_name", "slide_number")) and not (left and left == right):
            continue
        if left and right and left != right:
            continue
        return f"Preceding source passage:\n{prior['content']}\n\nCandidate passage:\n{base}"
    return base


def render_parent_plain(rows, index):
    return render_parent(rows, index, include_metadata=False)


def is_structured_table(row):
    meta = row["metadata"]
    return (meta.get("element_type") == "table" or meta.get("layout_type") == "table"
            or meta.get("chunking_method") == "table_row_groups" or meta.get("table_index") is not None)


def render_narrative_parent(rows, index):
    return rows[index]["content"] if is_structured_table(rows[index]) else render_parent_plain(rows, index)


def prepare(input_root=None):
    """Read canonical Git blobs in an ignored folder, preserving strict input hashes."""
    if input_root is not None:
        canonical = Path(input_root).resolve()
        commit = (canonical / "SNAPSHOT_COMMIT.txt").read_text(encoding="utf-8").strip()
    else:
        commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        canonical = ROOT / ".venv" / "source-context-inputs" / (commit + "-lf")
    if input_root is None and not canonical.exists():
        raw = subprocess.check_output(["git", "-c", "core.autocrlf=false", "archive", "--format=zip", commit,
            RELATIVE.as_posix(), "artifacts/evaluation/embedding-comparison-20261018"], cwd=ROOT)
        canonical.mkdir(parents=True)
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            for name in archive.namelist():
                check((canonical / name).resolve().is_relative_to(canonical.resolve()), "Invalid archive path")
            archive.extractall(canonical)
    candidate.ROOT = validator.ROOT = canonical
    snapshot = canonical / RELATIVE / "dense-evidence-benchmark-v1"
    previous.LABELS = canonical / RELATIVE / "evidence-v2/evidence.json"
    data = previous.load_experiment(snapshot)
    labels = canonical / RELATIVE / "evidence-v3/evidence.json"
    data["context"] = candidate.load_evidence_context(
        {"evidence": {"path": str(labels), "sha256": digest(labels.read_bytes())}}, data["cases"], data["rows"])
    data["provenance"].update(labels_sha256=digest(labels.read_bytes()), source_git_commit=commit)
    data["historical"] = json.loads((snapshot / "reranker-bge-v2-m3-v1/results.json").read_text(encoding="utf-8"))
    return data


def summarize(data, plain, context):
    records = []
    for case, indices, a, b in zip(data["cases"], data["candidates"], plain, context):
        check(np.isfinite(a).all() and np.isfinite(b).all(), "Incomplete scores")
        # Independent stable NumPy sort, separate from inference helper.
        ranks = {arm: np.asarray(indices)[np.argsort(-scores, kind="stable")].tolist()
                 for arm, scores in (("plain", a), ("source_context", b))}
        record = {"id": case["id"], "intent_id": case["intent_id"], "direction": case["direction"],
                  "candidate_chunk_ids": [previous.chunk_id(data["rows"][i]) for i in indices]}
        for arm, ranked in ranks.items():
            check(ranked[:10] == previous.rerank_candidates(indices, a if arm == "plain" else b), "Score sort mismatch")
            record[arm + "_evidence"] = previous.evidence_for(data, case, ranked[:10])
            record[arm + "_ranking"] = [previous.chunk_id(data["rows"][i]) for i in ranked]
        records.append(record)
    summary = {arm: previous.summaries(records, arm + "_evidence") for arm in ("plain", "source_context")}
    return records, summary


def main():
    global OUT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--input-root", type=Path, help="Canonical uploaded bundle; no Git checkout needed")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--device", choices=("cpu", "cuda"), default="cpu")
    parser.add_argument("--context-mode", choices=("metadata", "parent", "parent-plain", "narrative-parent"), default="metadata")
    parser.add_argument("--allow-download", action="store_true", help="Download pinned model on this execution host")
    args = parser.parse_args()
    render_input = {"metadata": render, "parent": render_parent, "parent-plain": render_parent_plain,
                    "narrative-parent": render_narrative_parent}[args.context_mode]
    if args.output_dir is not None:
        OUT = args.output_dir.resolve()
    if args.verify_only:
        report = json.loads((OUT / "results.json").read_text(encoding="utf-8"))
        data = prepare(args.input_root)
        config = report["configuration"]
        check(config.get("context_mode", "metadata") == args.context_mode, "Wrong context mode")
        check(config.get("control_mode", "plain") == ("metadata" if args.context_mode == "parent" else "plain"), "Wrong control mode")
        check(config["status"] == "completed" and config["provenance"] == data["provenance"], "Changed inputs")
        check(config == json.loads((OUT / "config.json").read_text(encoding="utf-8")), "Changed configuration")
        for name in ("plain", "context"):
            check(config[name + "_scores_sha256"] == digest((OUT / (name + "-scores.npy")).read_bytes()), "Changed score file")
        check(config["rendered_inputs_sha256"] == digest((OUT / "rendered-inputs.json").read_bytes()), "Changed rendered inputs")
        rendered = json.loads((OUT / "rendered-inputs.json").read_text(encoding="utf-8"))
        check(len(rendered) == len(data["rows"]), "Incomplete rendered inputs")
        for i, (row, saved) in enumerate(zip(data["rows"], rendered)):
            check(saved == {"chunk_id": previous.chunk_id(row), "original": row["content"],
                            "context_input": render_input(data["rows"], i)}, "Rendering differs")
        plain, context = [np.load(OUT / (name + "-scores.npy")) for name in ("plain", "context")]
        check(plain.shape == context.shape == (len(data["cases"]), 30), "Wrong score shape")
        for a, b, indices in zip(plain, context, data["candidates"]):
            for j, i in enumerate(indices):
                control = render(data["rows"], i) if args.context_mode == "parent" else data["rows"][i]["content"]
                if render_input(data["rows"], i) == control:
                    check(a[j] == b[j], "Unchanged pair score differs")
        records, summary = summarize(data, plain, context)
        check(records == report["results"] and summary == report["summary"], "Replay differs")
        audit = {"case_rankings_verified": len(records) * 2, "scores_verified": int(plain.size + context.size),
                 "independent_character_coverage": "passed", "rendering_and_input_hashes": "passed",
                 "results_sha256": digest((OUT / "results.json").read_bytes())}
        (OUT / "verification.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(audit, indent=2))
        return
    check(not (OUT / "results.json").exists(), "Completed outputs exist; preserve them")
    data = prepare(args.input_root)
    inputs = [render_input(data["rows"], i) for i in range(len(data["rows"]))]
    control_inputs = [render(data["rows"], i) if args.context_mode == "parent" else row["content"]
                      for i, row in enumerate(data["rows"])]
    pairs = [(case["question"], control_inputs[i]) for case, indices in zip(data["cases"], data["candidates"]) for i in indices]
    context_pairs = [(case["question"], inputs[i]) for case, indices in zip(data["cases"], data["candidates"]) for i in indices]
    from huggingface_hub import snapshot_download
    from transformers import AutoTokenizer, AutoConfig
    model_path = snapshot_download("BAAI/bge-reranker-v2-m3", revision=previous.REVISION,
        cache_dir=str(ROOT / ".venv/benchmark-model-cache"), local_files_only=not args.allow_download,
        allow_patterns=["config.json", "model.safetensors", "tokenizer.json", "tokenizer_config.json",
                        "special_tokens_map.json", "sentencepiece.bpe.model"])
    tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
    lengths = previous.check_pair_lengths(tokenizer, pairs + context_pairs, 1024)
    architecture = AutoConfig.from_pretrained(model_path, local_files_only=True)
    check(architecture.num_labels == 1 and architecture.max_position_embeddings - 2 >= 1024, "Wrong model architecture")
    OUT.mkdir(parents=True, exist_ok=True)
    config = {"status": "preflight", "revision": previous.REVISION, "model": "BAAI/bge-reranker-v2-m3",
              "context_mode": args.context_mode,
              "control_mode": "metadata" if args.context_mode == "parent" else "plain",
              "device": args.device, "dtype": "float32", "batch_size": 4, "threads": 4,
              "short_passage_max_chars": SHORT_CHARS, "candidate_k": 30, "final_k": 10,
              "context_token_budget": None, "max_pair_tokens": 1024, "truncated_pairs": 0,
              "max_observed_pair_tokens": max(lengths), "provenance": data["provenance"],
              "changed_pairs": sum(a != b for a, b in zip(pairs, context_pairs)),
              "runner_sha256": digest(Path(__file__).read_bytes()),
              "limits": "Post-hoc diagnostic on 20 paired intents; not held-out. Prefix is ranking-only; evidence uses unchanged original passages. Plain and context conditions use the same runtime; historical GPU FP16 scores are not this control."}
    (OUT / "rendered-inputs.json").write_text(json.dumps([
        {"chunk_id": previous.chunk_id(r), "original": r["content"], "context_input": rendered}
        for r, rendered in zip(data["rows"], inputs)], ensure_ascii=False, indent=2), encoding="utf-8")
    def save():
        (OUT / "config.json").write_text(json.dumps(config, indent=2) + "\n", encoding="utf-8")
    save()
    import torch
    from sentence_transformers import CrossEncoder
    check(args.device != "cuda" or torch.cuda.is_available(), "No GPU assigned; select a GPU runtime, no CPU fallback")
    torch.set_num_threads(4)
    started = perf_counter()
    model = CrossEncoder(model_path, device=args.device, max_length=1024, model_kwargs={"torch_dtype": torch.float32})
    config.update(model_load_seconds=perf_counter() - started, torch_version=torch.__version__,
                  gpu_name=torch.cuda.get_device_name(0) if args.device == "cuda" else None, status="running")
    model.predict(pairs[:1], show_progress_bar=False, activation_fn=torch.nn.Identity())
    plain = np.full((len(data["cases"]), 30), np.nan, dtype=np.float32)
    context = plain.copy()
    timings = []
    def predict(values):
        return np.asarray(model.predict(values, batch_size=4, show_progress_bar=False,
                          activation_fn=torch.nn.Identity(), convert_to_numpy=True), dtype=np.float32).reshape(-1)
    for n, (case, indices) in enumerate(zip(data["cases"], data["candidates"])):
        if args.device == "cuda":
            torch.cuda.synchronize()
        started = perf_counter()
        plain[n] = predict(pairs[n * 30:(n + 1) * 30])
        context[n] = plain[n]
        changed = [j for j, i in enumerate(indices) if inputs[i] != control_inputs[i]]
        if changed:
            context[n, changed] = predict([context_pairs[n * 30 + j] for j in changed])
        if args.device == "cuda":
            torch.cuda.synchronize()
        timings.append(perf_counter() - started)
        np.save(OUT / "plain-scores.npy", plain)
        np.save(OUT / "context-scores.npy", context)
        config.update(cases_completed=n + 1, paired_case_seconds=timings)
        save()
        print(f"{n + 1}/{len(data['cases'])} {case['id']} paired_seconds={timings[-1]:.1f} changed={len(changed)}", flush=True)
    # Load saved arrays again to validate the on-disk evidence, not just memory.
    records, summary = summarize(data, np.load(OUT / "plain-scores.npy"), np.load(OUT / "context-scores.npy"))
    config.update(status="completed", plain_scores_sha256=digest((OUT / "plain-scores.npy").read_bytes()),
                  context_scores_sha256=digest((OUT / "context-scores.npy").read_bytes()),
                  rendered_inputs_sha256=digest((OUT / "rendered-inputs.json").read_bytes()))
    save()
    (OUT / "results.json").write_text(json.dumps({"configuration": config, "summary": summary, "results": records},
                                                ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2), flush=True)


if __name__ == "__main__":
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
    main()
