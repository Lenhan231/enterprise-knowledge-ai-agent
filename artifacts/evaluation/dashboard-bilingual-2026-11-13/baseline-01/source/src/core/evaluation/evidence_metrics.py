"""Evaluation-only coverage of frozen evidence, independent of retrieval/model code."""
import hashlib


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _union(intervals):
    merged = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def score_evidence(evidence, intent_id, language, ranked_chunks, sources, k=10):
    """Score top-k chunks against AND requirements / OR alternative bundles.

    sources maps (document_id, parser_index) to frozen parser text for the target
    language. Chunks are {text, metadata}, with document_id and source mapping
    in metadata. Missing/stale/invalid mappings raise ValueError, never a miss.
    Only whitespace gaps are ignored; numbers and punctuation must be covered.
    Duplicate chunks consume ranking slots but never inflate evidence coverage.
    This checks annotated evidence retrieval, not generated-answer correctness.
    """
    _require(type(k) is int and k > 0, "k must be a positive integer")
    _require(language in evidence["sources"], "Unknown evidence language")
    intent = next((q for q in evidence["intents"] if q["id"] == intent_id), None)
    _require(intent is not None, "Unknown intent")
    intervals = {}
    selected = list(ranked_chunks)[:k]
    for rank, chunk in enumerate(selected, 1):
        meta = chunk.get("metadata", {})
        key = (meta.get("document_id"), meta.get("source_parser_index"))
        _require(key in sources, f"Rank {rank}: unknown source or missing provenance")
        source = sources[key]
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        _require(meta.get("source_content_sha256") == digest, f"Rank {rank}: source hash mismatch")
        text = chunk.get("text")
        spans = meta.get("source_spans")
        _require(isinstance(text, str) and isinstance(spans, list) and spans,
                 f"Rank {rank}: missing source mapping")
        child_intervals = []
        for span in spans:
            coords = [span.get(name) for name in ("source_start", "source_end", "chunk_start", "chunk_end")]
            _require(all(type(n) is int for n in coords), f"Rank {rank}: invalid coordinates")
            a, b, c, d = coords
            _require(0 <= a < b <= len(source) and 0 <= c < d <= len(text),
                     f"Rank {rank}: coordinates out of bounds")
            _require(b-a == d-c and source[a:b] == text[c:d], f"Rank {rank}: mapped text mismatch")
            child_intervals.append((c, d))
            intervals.setdefault(key, []).append((a, b))
        previous = 0
        for c, d in _union(child_intervals):
            _require(not text[previous:c].strip(), f"Rank {rank}: unmapped content")
            previous = d
        _require(not text[previous:].strip(), f"Rank {rank}: unmapped content")
    intervals = {key: _union(parts) for key, parts in intervals.items()}
    coverage = {}

    def span_result(sid):
        if sid in coverage:
            return coverage[sid]
        span = evidence["spans"][sid]
        _require(span["language"] == language, f"Wrong-language label {sid}")
        key = (span["document_id"], span["source_parser_index"])
        _require(key in sources, f"Missing label source {sid}")
        source = sources[key]
        _require(hashlib.sha256(source.encode("utf-8")).hexdigest() == span["source_content_sha256"],
                 f"Changed label source {sid}")
        a, b = span["start_char"], span["end_char"]
        _require(type(a) is int and type(b) is int and 0 <= a < b <= len(source)
                 and source[a:b] == span["quote"] and bool(span["quote"].strip()), f"Invalid label {sid}")
        total = sum(not ch.isspace() for ch in source[a:b])
        covered = sum(sum(not ch.isspace() for ch in source[max(a,c):min(b,d)])
                      for c, d in intervals.get(key, []) if max(a,c) < min(b,d))
        result = {"covered_characters": covered, "total_characters": total,
                  "fraction": covered / total, "complete": covered == total}
        coverage[sid] = result
        return result

    requirements = []
    for requirement in intent["requirements"]:
        status = requirement["status"]
        result = {"id": requirement["id"], "required": requirement["required"], "status": status}
        if status == "ready":
            alternatives = requirement["evidence_by_language"][language]["alternatives"]
            _require(bool(alternatives) and all(a["all_of"] for a in alternatives), "Empty evidence bundle")
            bundles = []
            for alternative in alternatives:
                ids = alternative["all_of"]
                bundles.append({"all_of": ids, "complete": all([span_result(s)["complete"] for s in ids]),
                                "missing_spans": [s for s in ids if not span_result(s)["complete"]]})
            result.update(complete=any(b["complete"] for b in bundles), alternatives=bundles)
        else:
            result["complete"] = None
        requirements.append(result)
    scored = [r for r in requirements if r["required"] and r["status"] == "ready"]
    eligible = all(r["status"] == "ready" for r in requirements if r["required"]) and bool(scored)
    met = sum(r["complete"] for r in scored)
    return {"intent_id": intent_id, "language": language, "k": k, "chunks_scored": len(selected),
            "required_ready": len(scored), "required_met": met,
            "required_coverage": met / len(scored) if scored else None,
            "full_intent_eligible": eligible,
            "full_evidence_success": met == len(scored) if eligible else None,
            "requirements": requirements, "span_coverage": coverage}
