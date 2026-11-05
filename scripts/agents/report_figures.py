#!/usr/bin/env python3
"""Figures for the evaluation chapter, drawn from the scored run files.

Needs matplotlib, which is not a project dependency: run it with any Python that has it, e.g.
  uv venv /tmp/figenv && VIRTUAL_ENV=/tmp/figenv uv pip install matplotlib
  /tmp/figenv/bin/python scripts/agents/report_figures.py
"""
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "artifacts/local/vietstyle-runs"
OUT = ROOT / "docs/report/figures"
# Validated categorical slots (dataviz reference palette, light surface).
BLUE, ORANGE, AQUA, YELLOW = "#2a78d6", "#eb6834", "#1baf7a", "#eda100"
INK, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#e6e5e1", "#fcfcfb"
ARMS = [("B0", "Closed-book"), ("B1", "Naive RAG"), ("B2", "Tuned RAG"),
        ("B4", "Tuned RAG,\nno verifier"), ("E2E-K", "API: Knowledge\nmode"), ("E2E", "API: Auto mode")]

plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9, "axes.edgecolor": GRID,
                     "axes.labelcolor": MUTED, "xtick.color": MUTED, "ytick.color": MUTED,
                     "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.dpi": 200})


def rows(arm, judge):
    name = f"{arm}.scored.json" if judge == "A" else f"{arm}.scored.codex.json"
    return [r for r in json.loads((RUNS / name).read_text())["rows"] if r.get("judge")]


def wilson(k, n, z=1.96):
    p = k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return centre - half, centre + half


def recessive(ax, axis="x"):
    ax.grid(axis=axis, color=GRID, linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)


def accuracy_figure():
    fig, ax = plt.subplots(figsize=(6.8, 3.6))
    y = list(range(len(ARMS)))[::-1]
    for offset, judge, colour, label in ((0.18, "A", BLUE, "Judge A (gpt-oss-120b)"), (-0.18, "B", ORANGE, "Judge B (Codex)")):
        for yi, (arm, _) in zip(y, ARMS):
            data = rows(arm, judge)
            k, n = sum(r["judge"]["correctness"] == "correct" for r in data), len(data)
            lo, hi = wilson(k, n)
            ax.barh(yi + offset, k / n * 100, height=0.32, color=colour, label=label if arm == "B0" else None)
            ax.errorbar(k / n * 100, yi + offset, xerr=[[(k / n - lo) * 100], [(hi - k / n) * 100]],
                        fmt="none", ecolor=MUTED, elinewidth=1, capsize=2)
            ax.text(hi * 100 + 1.5, yi + offset, f"{k / n:.0%}", va="center", color=INK, fontsize=8)
    ax.set_yticks(y, [name for _, name in ARMS], color=INK)
    ax.set_xlim(0, 100)
    ax.set_xlabel("Answers judged correct (%), with 95% Wilson interval")
    recessive(ax)
    ax.legend(loc="lower right", frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig6-2-accuracy-by-configuration.png")


def failure_mode_figure():
    labels = ("Answered, correct", "Answered, partial", "Answered, wrong", "Refused or withheld")
    colours = (BLUE, AQUA, ORANGE, YELLOW)
    fig, ax = plt.subplots(figsize=(6.8, 2.2))
    for yi, (arm, name) in enumerate((("E2E-K", "API: Knowledge mode"), ("B2", "Tuned RAG"))):
        answerable = [r for r in rows(arm, "A") if not r["should_abstain"]]
        refused = lambda r: bool(r.get("refusal")) or bool(r["judge"].get("abstained"))
        counts = [sum(not refused(r) and r["judge"]["correctness"] == c for r in answerable)
                  for c in ("correct", "partial", "incorrect")] + [sum(refused(r) for r in answerable)]
        left = 0
        for count, colour, label in zip(counts, colours, labels):
            ax.barh(yi, count, left=left, height=0.55, color=colour, edgecolor=SURFACE, linewidth=2,
                    label=label if yi == 0 else None)
            if count:
                ax.text(left + count / 2, yi, str(count), ha="center", va="center", color=INK, fontsize=8)
            left += count
        ax.text(left + 0.8, yi, f"n = {len(answerable)}", va="center", color=MUTED, fontsize=8)
    ax.set_yticks([0, 1], ["API: Knowledge mode", "Tuned RAG"], color=INK)
    ax.set_xlabel("Answerable questions (judge A)")
    recessive(ax)
    ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.45), ncol=4, frameon=False, fontsize=8)
    fig.tight_layout()
    fig.savefig(OUT / "fig6-3-failure-modes.png", bbox_inches="tight")


def latency_figure():
    # Warm-pass stage medians, run parallel-db-01 (3 Nov 2026, V1-V6, Knowledge mode, verifier on).
    stages = [("Database wait", 2.7), ("Reranking (mMiniLM)", 1.5), ("Answer generation", 0.84),
              ("Claim verification", 0.59), ("Search planning", 0.41), ("Query embedding", 0.06)]
    fig, ax = plt.subplots(figsize=(6.8, 2.6))
    y = list(range(len(stages)))[::-1]
    ax.barh(y, [s for _, s in stages], height=0.5, color=BLUE)
    for yi, (_, s) in zip(y, stages):
        ax.text(s + 0.05, yi, f"{s:.2f} s", va="center", color=INK, fontsize=8)
    ax.set_yticks(y, [n for n, _ in stages], color=INK)
    ax.set_xlabel("Median stage time (s); end-to-end median 6.7 s")
    ax.set_xlim(0, 3.3)
    recessive(ax)
    fig.tight_layout()
    fig.savefig(OUT / "fig6-1-latency-stages.png")


def flow_figure():
    fig, ax = plt.subplots(figsize=(8.4, 3.0))
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 40)
    ax.axis("off")

    def box(x, y, w, text, dashed=False):
        ax.add_patch(FancyBboxPatch((x, y), w, 7, boxstyle="round,pad=0.4,rounding_size=1.2",
                                    facecolor="#eef4fc" if not dashed else SURFACE,
                                    edgecolor=BLUE if not dashed else MUTED, linewidth=1,
                                    linestyle="--" if dashed else "-"))
        ax.text(x + w / 2, y + 3.5, text, ha="center", va="center", color=INK, fontsize=7.2)

    def arrow(x1, y1, x2, y2):
        ax.add_patch(FancyArrowPatch((x1, y1), (x2, y2), arrowstyle="-|>", mutation_scale=8, color=MUTED, linewidth=1))

    steps = ["Question", "Query\ntranslation", "Dense + EN/VI BM25\n(RRF fusion)", "Rerank top 30\n(keep top 5)",
             "Cited answer\n(Qwen 27B)", "Claim\nverification", "Answer"]
    xs = [1, 14, 27, 44, 58, 72, 87]
    widths = [10, 10, 14, 11, 11, 11, 10]
    for x, w, s in zip(xs, widths, steps):
        box(x, 14, w, s)
    for (x, w), nx in zip(zip(xs, widths), xs[1:]):
        arrow(x + w + 0.6, 17.5, nx - 0.6, 17.5)
    box(14, 29, 24, "Auto mode: planner routes and\nrewrites the task question", dashed=True)
    box(58, 29, 24, "Auto mode: synthesis step with\nnumber guard", dashed=True)
    box(27, 1, 28, "Knowledge mode: optional split into\ntwo search queries", dashed=True)
    # Dotted connectors show where each mode-specific step acts on the shared flow.
    for xs_, ys_ in (([20, 20, 12.5, 12.5], [28.6, 24.5, 24.5, 18.4]),   # planner: before translation
                     ([76, 76, 85, 85], [28.6, 24.5, 24.5, 18.4]),       # synthesis: after verification
                     ([34, 34], [8.4, 13.6])):                           # query split: at retrieval
        ax.plot(xs_, ys_, linestyle=":", color=MUTED, linewidth=1)
    ax.text(50, 38.5, "Solid: shared Knowledge pipeline.  Dashed: mode-specific steps.", ha="center",
            color=MUTED, fontsize=7.2)
    fig.tight_layout()
    fig.savefig(OUT / "fig5-1-knowledge-flow.png", bbox_inches="tight")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    accuracy_figure()
    failure_mode_figure()
    latency_figure()
    flow_figure()
    print("wrote", sorted(p.name for p in OUT.glob("*.png")))
