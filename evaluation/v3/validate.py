"""Check vietstyle-v3 dev/test sets against SPEC.md: shape, balance, gold passages, and dev/test leakage.

Usage: python evaluation/v3/validate.py <chunks.jsonl> [set_dir]
Exit code 1 when any error is found; warnings (near-duplicate questions) do not fail.
"""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

CATEGORIES = ["lookup", "amount", "calculation", "multi_part", "multi_passage", "table", "not_covered",
              "false_premise", "language", "noisy", "rbac", "follow_up"]
PER_CATEGORY = 5
ROLES = {"employee", "finance_analyst", "sustainability_analyst", "procurement", "operations", "legal_compliance",
         "executive", "admin", "document_uploader", "document_processing_owner"}
OUTCOMES = {"answer", "not_covered", "clarify"}
# Money facts allowed per split (SPEC.md "Splitting dev and test").
FACTS = {"dev": {"F2.tier1", "F2.tier2", "F3.tier1", "F3.tier2", "F3.total"},
         "test": {"F1.meal", "F1.lodging", "F2.tier3", "F3.tier3", "F3.tier4", "F3.total_test"}}


def trigrams(text):
    text = unicodedata.normalize("NFC", text.lower())
    text = re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", text)).strip()
    return {text[i:i + 3] for i in range(len(text) - 2)}


def main(chunks_path, set_dir="artifacts/evaluation/vietstyle-v3"):
    set_dir = Path(set_dir)
    corpus = {(r["document_name"], r["chunk_index"]): r for r in map(json.loads, open(chunks_path, encoding="utf-8"))}
    split = json.load(open(set_dir / "split.json", encoding="utf-8"))
    owner = {}  # (document, chunk_index) -> dev | test | shared_by_fact
    for topic in split["topics"]:
        for lang in ("vn", "en"):
            for index in topic[lang]:
                owner[(split["documents"][lang], index)] = topic["split"]
    for name in ("dev", "test"):
        for document, index in split["pack"][name]:
            owner[(document, index)] = name

    errors, warnings, sets = [], [], {}
    for name in ("dev", "test"):
        path = set_dir / f"{name}-v3.json"
        if not path.exists():
            warnings.append(f"{path} missing")
            continue
        items = json.load(open(path, encoding="utf-8"))["items"]
        sets[name] = items
        counts = Counter(item["category"] for item in items)
        for category in CATEGORIES:
            if counts[category] != PER_CATEGORY:
                errors.append(f"{name}: category {category} has {counts[category]} items, expected {PER_CATEGORY}")
        for category in set(counts) - set(CATEGORIES):
            errors.append(f"{name}: unknown category {category}")
        ids = [item["id"] for item in items]
        if len(ids) != len(set(ids)):
            errors.append(f"{name}: duplicate ids")
        for item in items:
            where = f'{name}:{item["id"]}'
            if item.get("role") not in ROLES:
                errors.append(f"{where}: unknown role {item.get('role')}")
            if item.get("expected_outcome") not in OUTCOMES:
                errors.append(f"{where}: bad expected_outcome")
            if item.get("language") not in {"vi", "en", "mixed"}:
                errors.append(f"{where}: bad language")
            if not item.get("question", "").strip() or not item.get("reference_answer", "").strip():
                errors.append(f"{where}: question and reference_answer are required")
            if item["category"] == "follow_up" and not item.get("history"):
                errors.append(f"{where}: follow_up needs history")
            gold = item.get("gold", [])
            if item.get("expected_outcome") == "answer":
                if not gold or not any(g["grade"] == 2 for g in gold):
                    errors.append(f"{where}: an answer item needs at least one grade-2 gold passage")
                if not item.get("must_include"):
                    errors.append(f"{where}: an answer item needs must_include")
            for g in gold:
                key = (g["document"], g["chunk_index"])
                if key not in corpus:
                    errors.append(f"{where}: gold {key} is not in the corpus")
                    continue
                if g["grade"] not in (1, 2):
                    errors.append(f"{where}: grade must be 1 or 2")
                home = owner.get(key)
                if g.get("source") == "pool":
                    # Judged relevant after authoring: the policy repeats some rules across topics, so this is reported, not refused.
                    if home not in (name, "shared_by_fact"):
                        warnings.append(f"{where}: pooled gold {key} comes from {home} topics (repeated fact)")
                    continue
                if home not in (name, "shared_by_fact"):
                    errors.append(f"{where}: gold {key} belongs to {home}, not {name}")
                roles = set((corpus[key].get("document") or {}).get("allowed_roles") or [])
                if item.get("expected_outcome") == "answer" and item["role"] != "admin" and item["role"] not in roles:
                    errors.append(f"{where}: role {item['role']} cannot retrieve gold {key} (allowed {sorted(roles)})")
                if home == "shared_by_fact" and not set(item.get("facts", [])) & FACTS[name]:
                    errors.append(f"{where}: a shared money passage needs a {name} fact id")
            for fact in item.get("facts", []):
                other = "test" if name == "dev" else "dev"
                if fact in FACTS[other]:
                    errors.append(f"{where}: fact {fact} belongs to {other}")

    if len(sets) == 2:
        dev_gold = {(g["document"], g["chunk_index"]) for i in sets["dev"] for g in i.get("gold", []) if g.get("source") != "pool"}
        test_gold = {(g["document"], g["chunk_index"]) for i in sets["test"] for g in i.get("gold", []) if g.get("source") != "pool"}
        for key in sorted((dev_gold & test_gold) - {k for k, v in owner.items() if v == "shared_by_fact"}):
            errors.append(f"gold passage {key} is used by both dev and test")
    everything = [(n, i) for n, items in sets.items() for i in items]
    grams = [(n, i, trigrams(i["question"])) for n, i in everything]
    for a in range(len(grams)):
        for b in range(a + 1, len(grams)):
            union = grams[a][2] | grams[b][2]
            score = len(grams[a][2] & grams[b][2]) / len(union) if union else 0
            if score >= 0.5:
                warnings.append(f"near-duplicate ({score:.2f}): {grams[a][0]}:{grams[a][1]['id']} ~ "
                                f"{grams[b][0]}:{grams[b][1]['id']}")
    for line in warnings:
        print("WARN ", line)
    for line in errors:
        print("ERROR", line)
    print(f"{sum(len(v) for v in sets.values())} items checked, {len(errors)} errors, {len(warnings)} warnings")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
