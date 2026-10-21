"""Shared local MinerU runtime used by its format adapters."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .result_mapper import MineruResultMapper

logger = logging.getLogger(__name__)


class MineruProcessor:
    """Provide shared MinerU execution and dispatch to a format adapter."""

    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.result_mapper = MineruResultMapper(config)

    def process(self, source: bytes | str | Path, file_path: str | None, document: dict[str, Any]) -> dict[str, Any]:
        from .formats.router import process

        source_format = str(document.get("metadata", {}).get("format", "PDF")).lower()
        content = source if isinstance(source, bytes) else Path(source).read_bytes()
        return process(self, content, source_format, document)

    def run(self, arguments: list[str]) -> subprocess.CompletedProcess:
        cli = os.getenv("MINERU_LOCAL_CLI", "mineru-kit")
        executable = shutil.which(cli) if not Path(cli).is_absolute() else cli
        if not executable or not Path(executable).is_file():
            raise RuntimeError(
                "Local MinerU is unavailable; install MinerU in an isolated environment "
                "and set MINERU_LOCAL_CLI to its mineru-kit executable"
            )
        try:
            completed = subprocess.run(
                [executable, *arguments], capture_output=True, text=True, timeout=1200,
                check=False, env=self._runtime_environment(),
            )
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Local MinerU timed out after 20 minutes") from error
        except OSError as error:
            raise RuntimeError(f"Could not start local MinerU: {type(error).__name__}") from error
        if completed.returncode:
            detail = (completed.stderr or completed.stdout or "").strip()[-1200:]
            raise RuntimeError(f"Local MinerU failed (exit {completed.returncode}): {detail}")
        return completed

    def parse_flash(self, content: bytes, source_format: str, document: dict[str, Any]) -> dict[str, Any]:
        with tempfile.TemporaryDirectory(prefix="upload-test-mineru-") as temporary_dir:
            work_dir = Path(temporary_dir)
            input_path = work_dir / f"input.{source_format}"
            output_dir = work_dir / "output"
            input_path.write_bytes(content)
            self.run(["parse", str(input_path), "--output", str(output_dir), "--tier", "flash"])
            markdown_files = list(output_dir.rglob("*.md")) if output_dir.exists() else []
            if len(markdown_files) != 1:
                raise RuntimeError(
                    f"Local MinerU produced {len(markdown_files)} Markdown files; expected one"
                )
            try:
                markdown = markdown_files[0].read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError) as error:
                raise RuntimeError("Local MinerU produced unreadable Markdown") from error
        return self.result_mapper.markdown_result(markdown, document)

    @staticmethod
    def _runtime_environment() -> dict[str, str]:
        environment = os.environ.copy()
        environment["MINERU_MODEL_SOURCE"] = "local"
        mineru_home = os.getenv("MINERU_LOCAL_HOME")
        if mineru_home:
            environment["HOME"] = mineru_home
        return environment
