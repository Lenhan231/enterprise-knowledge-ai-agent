#!/usr/bin/env python3
"""Compatibility entry point for the active Commerce decision benchmark."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.agents.evaluate_commerce_decision_support import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
