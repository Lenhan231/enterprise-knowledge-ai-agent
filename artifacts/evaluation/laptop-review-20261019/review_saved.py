"""Replay committed benchmark vectors locally, without encoders or services."""

import hashlib
import json
from pathlib import Path
import re
from statistics import mean

import numpy as np

HERE = Path(__file__).resolve().parent
EVALUATION = HERE.parent


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def verify_file(path, expected, checks):
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    status = "exact bytes"
    if actual != expected:
        # Git autocrlf changes text checkout bytes on this Windows laptop.
        assert hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest() == expected, path
        status = "matches after CRLF-to-LF normalization; checkout bytes differ"
    checks.append({"file": path.relative_to(EVALUATION.parents[1]).as_posix(), "status": status})


def replay(folder, checks):
    setup = load(folder / "benchmark-config.json")
    manifest = load(folder / "manifest.json")
    corpus_path, case_path = folder / setup["indexed_corpus"], folder / setup["cases"]
    verify_file(corpus_path, setup["indexed_corpus_sha256"], checks)
    verify_file(case_path, manifest[setup["cases"] + "_sha256"], checks)
    rows = [json.loads(line) for line in corpus_path.read_text(encoding="utf-8").splitlines()]
    cases = load(case_path)["cases"]
    assert {r["document_id"] for r in rows} == set(setup["document_ids"])
    if "pages_sha256" in manifest:
        verify_file(folder / "pages.jsonl", manifest["pages_sha256"], checks)
        verify_file(folder / "retained-original-contexts.json", manifest["retained_contexts_sha256"], checks)
        for name, digest in manifest["original_pdf_sha256"].items():
            verify_file(EVALUATION.parents[1] / "data/raw/benchmark_data" / name, digest, checks)
        for page in map(json.loads, (folder / "pages.jsonl").read_text(encoding="utf-8").splitlines()):
            words = list(re.finditer(r"\S+", page["content"]))
            chunks = [r for r in rows if r["document_id"] == page["document_id"] and r["metadata"]["page_number"] == page["page_number"]]
            covered = set()
            for row in chunks:
                start, end = row["metadata"]["word_start"], row["metadata"]["word_end"]
                assert row["content"] == page["content"][words[start].start():words[end - 1].end()]
                covered.update(range(start, end))
            assert covered == set(range(len(words))), (page["document_id"], page["page_number"])
    if "parser_corpus_sha256" in manifest:
        verify_file(folder / "parser-corpus.jsonl", manifest["parser_corpus_sha256"], checks)
    row_order_hash = hashlib.sha256(json.dumps([(r["document_id"], r["chunk_index"]) for r in rows]).encode()).hexdigest()
    variants = [(p.name, p) for p in sorted((folder / "candidates").iterdir()) if (p / "results.json").exists()]
    if "vectors_file" in setup:
        variants.insert(0, ("baseline", folder))
    output = {}
    for name, path in variants:
        baseline = name == "baseline"
        report = load(path / ("baseline-local-replay.json" if baseline else "results.json"))
        config = setup if baseline else load(path / "config.json")
        vector_path = path / (setup["vectors_file"] if baseline else "vectors.npy")
        query_path = path / ("baseline-query-vectors.npy" if baseline else "query-vectors.npy")
        verify_file(vector_path, config["vectors_file_sha256"], checks)
        if not baseline:
            assert config == report["configuration"]
            assert config["status"] == "completed" and config["truncated_inputs"] == 0
            assert config["corpus_sha256"] == setup["indexed_corpus_sha256"]
            assert config["cases_sha256"] == manifest[setup["cases"] + "_sha256"]
            assert config["row_order_sha256"] == row_order_hash
            assert config["revision"]
        vectors = np.load(vector_path, allow_pickle=False)
        queries = np.load(query_path, allow_pickle=False)
        assert vectors.shape[0] == len(rows) and queries.shape == (len(cases), vectors.shape[1])
        assert np.isfinite(vectors).all() and np.isfinite(queries).all()
        vn, qn = np.linalg.norm(vectors, axis=1), np.linalg.norm(queries, axis=1)
        assert (vn > 0).all() and (qn > 0).all()
        if not baseline:
            assert np.allclose(vn, 1, atol=1e-5) and np.allclose(qn, 1, atol=1e-5)
        vectors, queries = vectors / vn[:, None], queries / qn[:, None]
        saved = report["results"]
        assert [r["id"] for r in saved] == [c["id"] for c in cases]
        if baseline:
            original = load(folder / "dense-baseline.json")["results"]
            assert [r["id"] for r in original] == [c["id"] for c in cases]
            for replayed, recorded in zip(saved, original):
                assert replayed["ranked_chunk_ids"] == [c["chunk_id"] for c in recorded["retrieved_contexts"]]
        reviewed = []
        for case, query, stored in zip(cases, queries, saved):
            roles = set(case["allowed_roles"])
            eligible = np.array([i for i, row in enumerate(rows) if "admin" in roles or roles.intersection(row["allowed_roles"])], dtype=int)
            scores = vectors[eligible] @ query
            order = eligible[np.argsort(-scores, kind="stable")]
            top = order[:10]
            ids = [f"{rows[i]['document_id']}::chunk::{rows[i]['chunk_index']}" for i in top]
            assert ids == stored["ranked_chunk_ids"], (folder.name, name, case["id"])
            expected = set(case["expected_sources"])
            found = {Path(rows[i]["document_name"]).name for i in top} & expected
            recall = len(found) / len(expected)
            assert abs(recall - stored["source_recall_at_10"]) < 1e-8
            item = {"id": case["id"], "question": case["question"], "source_recall_at_10": recall}
            if "gold_pages" in case:
                gold = set(case["gold_pages"])
                pages = [f"{rows[i]['document_id']}::page::{rows[i]['metadata']['page_number']}" for i in order]
                hits = gold.intersection(pages[:10])
                page_recall = len(hits) / len(gold)
                rr = next((1 / rank for rank, page in enumerate(pages[:10], 1) if page in gold), 0)
                assert abs(page_recall - stored["evidence_page_recall_at_10"]) < 1e-8
                assert abs(rr - stored["evidence_page_reciprocal_rank_at_10"]) < 1e-8
                ranks = {page: pages.index(page) + 1 for page in gold}
                best = min(ranks.values())
                best_index = order[best - 1]
                item.update(direction=case["direction"], gold_page_ranks=ranks,
                            page_recall_at_10=page_recall, reciprocal_rank_at_10=rr,
                            distinct_pages_in_top10=len(set(pages[:10])),
                            top1={"chunk_id": ids[0], "page": pages[0], "text": rows[top[0]]["content"]},
                            best_gold={"rank": best, "chunk_index": rows[best_index]["chunk_index"],
                                       "page": pages[best - 1], "text": rows[best_index]["content"]},
                            top10=[{"rank": rank, "page": pages[rank - 1], "chunk_id": ids[rank - 1],
                                    "text": rows[index]["content"]} for rank, index in enumerate(top, 1)])
            reviewed.append(item)
        summary = {"rankings_verified": len(cases), "mean_source_recall_at_10": mean(x["source_recall_at_10"] for x in reviewed)}
        if "gold_pages" in cases[0]:
            summary.update(by_direction={d: {
                "cases": len(group := [x for x in reviewed if x["direction"] == d]),
                "page_recall_at_10": mean(x["page_recall_at_10"] for x in group),
                "mrr_at_10": mean(x["reciprocal_rank_at_10"] for x in group),
                "zero_gold_page_hits": sum(x["page_recall_at_10"] == 0 for x in group),
            } for d in sorted({x["direction"] for x in reviewed})},
                           mean_distinct_pages_in_top10=mean(x["distinct_pages_in_top10"] for x in reviewed))
            for d, group in summary["by_direction"].items():
                saved_group = report["summary"]["by_direction"][d]
                assert abs(group["page_recall_at_10"] - saved_group["mean_evidence_page_recall_at_10"]) < 1e-8
                assert abs(group["mrr_at_10"] - saved_group["mrr_at_10"]) < 1e-8
        else:
            recorded = report.get("summary", {}).get("mean_source_recall_at_10", report.get("local_mean_source_recall_at_10"))
            assert abs(summary["mean_source_recall_at_10"] - recorded) < 1e-8
        output[name] = {"summary": summary, "cases": reviewed}
    return output


if __name__ == "__main__":
    checks = []
    output = {name: replay(EVALUATION / name, checks) for name in (
        "embedding-comparison-20261018", "four-direction-20261018",
    )}
    result = {"file_checks": checks, "experiments": output,
              "limits": "Saved-vector replay verifies rankings/metrics, not encoder execution, tokenizer audits or answer correctness. No database/model/network access."}
    (HERE / "verification.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    models = output["four-direction-20261018"]
    names = list(models)
    lines = ["# First labeled evidence-page rank in the full corpus", "",
             "Ranks are recomputed from saved vectors. A rank over 10 is a miss at the reported cutoff.",
             "A page hit does not guarantee that the chunk contains the answer.", "",
             "| Query | Direction | " + " | ".join(names) + " |",
             "|---|---|" + "---:|" * len(names)]
    for index, case in enumerate(models[names[0]]["cases"]):
        lines.append(f"| {case['id']} | {case['direction']} | " + " | ".join(
            str(models[name]["cases"][index]["best_gold"]["rank"]) for name in names) + " |")
    (HERE / "gold-page-ranks.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    count = sum(data["summary"]["rankings_verified"] for models in output.values() for data in models.values())
    print(f"Verified {count} top-ten orders and case metrics; {len(checks)} file hash checks.")
    print("Wrote verification.json and gold-page-ranks.md; no encoders or services used.")
