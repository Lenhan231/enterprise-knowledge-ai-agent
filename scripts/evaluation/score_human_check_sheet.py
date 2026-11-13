"""Compare the filled blind sheet with the three judges and their majority: agreement and Cohen's kappa."""
import json
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
base = Path(sys.argv[1])
sheet = (base / "judge-review-20261111.md").read_text(encoding="utf-8")
key = json.loads((base / "judge-review-20261111.key.json").read_text(encoding="utf-8"))


def norm(text):
    t = unicodedata.normalize("NFC", text).strip().lower()
    if re.match(r"^(một phần|mot phan|partial)", t):
        return "partial"
    if re.match(r"^(đúng|dung|correct)", t):
        return "correct"
    if re.match(r"^(sai|incorrect|wrong)", t):
        return "incorrect"
    return None


human, missing = {}, []
for block in re.split(r"^## ", sheet, flags=re.M)[1:]:
    n = int(block.split(".", 1)[0])
    m = re.search(r"\*\*Người chấm:\*\*\s*(.*)", block)
    grade = norm(m.group(1)) if m and m.group(1).strip() else None
    if grade is None:
        missing.append(n)
    else:
        human[n] = grade

if missing:
    print("Not graded or unreadable grade (use đúng / một phần / sai):", missing)


def kappa(x, y):
    n = len(x)
    po = sum(a == b for a, b in zip(x, y)) / n
    cx, cy = Counter(x), Counter(y)
    pe = sum(cx[c] * cy[c] for c in set(cx) | set(cy)) / (n * n)
    return po, (po - pe) / (1 - pe) if pe < 1 else float("nan")


items = [i for i in key["items"] if i["n"] in human]
h = [human[i["n"]] for i in items]
print(f"Graded: {len(items)} of {len(key['items'])}")
if not items:
    sys.exit(0)
for judge in ("A", "B", "C", "majority"):
    j = [i[judge] for i in items]
    po3, k3 = kappa(h, j)
    po2, k2 = kappa(["correct" if g == "correct" else "not" for g in h],
                    ["correct" if g == "correct" else "not" for g in j])
    print(f"{judge:>8}: three-way agreement {po3:.0%} (kappa {k3:.2f}); correct vs not {po2:.0%} (kappa {k2:.2f})")
print("\nDisagreements with the majority:")
for i in items:
    if human[i["n"]] != i["majority"]:
        print(f"  #{i['n']} {i['run']} {i['id']}: human {human[i['n']]}, A/B/C {i['A']}/{i['B']}/{i['C']}")
accepted_wrong = [i for i in items if i["majority"] == "correct" and human[i["n"]] != "correct"]
print(f"\nMajority called correct but human did not: {len(accepted_wrong)}")
