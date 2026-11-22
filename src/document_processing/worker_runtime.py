"""Interpreter paths and import environment for isolated model workers."""

from __future__ import annotations

import os
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SOURCE_ROOT.parent


def worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(SOURCE_ROOT), env.get("PYTHONPATH", "")])
    )
    return env
