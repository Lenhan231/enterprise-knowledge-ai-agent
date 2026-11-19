"""Interpreter paths and import environment for isolated model workers."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any


SOURCE_ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = SOURCE_ROOT.parent


def resolve_invoice_worker_python(config: dict[str, Any] | None = None) -> Path | None:
    """Find the isolated runtime used by local invoice text extraction."""
    configured = (config or {}).get("invoice_worker_python") or os.environ.get(
        "DOCUMENT_PROCESSING_INVOICE_WORKER_PYTHON"
    )
    if configured:
        return Path(str(configured)).expanduser()
    local_python = PROJECT_ROOT / ".venv-invoice-worker" / "bin" / "python"
    return local_python if local_python.is_file() else None


def worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(SOURCE_ROOT), env.get("PYTHONPATH", "")])
    )
    return env
