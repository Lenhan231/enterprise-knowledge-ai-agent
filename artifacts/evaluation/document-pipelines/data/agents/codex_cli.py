"""Shared, read-only Codex CLI transport for review agents."""

from __future__ import annotations

import io
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TypeVar

from PIL import Image
from pydantic import BaseModel

MAX_CODEX_IMAGE_BYTES = 14 * 1024 * 1024
Draft = TypeVar("Draft", bound=BaseModel)


def prepare_codex_image(image_bytes: bytes) -> bytes:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGB")
        quality = 92
        while True:
            buffer = io.BytesIO()
            image.save(buffer, format="JPEG", quality=quality, optimize=True)
            prepared = buffer.getvalue()
            if len(prepared) <= MAX_CODEX_IMAGE_BYTES:
                return prepared
            if quality > 82:
                quality -= 5
                continue
            if max(image.size) <= 1800:
                raise ValueError("Page image is too large to send to Codex CLI")
            image.thumbnail((int(image.width * 0.85), int(image.height * 0.85)), Image.Resampling.LANCZOS)
            quality = 88


def run_codex_json(
    images: list[tuple[str, bytes]],
    prompt: str,
    schema: dict,
    temp_prefix: str,
    output_filename: str,
    draft_type: type[Draft],
) -> tuple[Draft, str]:
    executable = shutil.which("codex")
    if executable is None:
        raise RuntimeError("Codex CLI is not installed or is missing from the review server PATH")
    model = "Codex CLI configured model"
    with tempfile.TemporaryDirectory(prefix=temp_prefix) as temp_dir:
        temp_path = Path(temp_dir)
        image_paths = []
        for filename, image_bytes in images:
            image_path = temp_path / filename
            image_path.write_bytes(prepare_codex_image(image_bytes))
            image_paths.append(image_path)
        schema_path = temp_path / "draft-schema.json"
        output_path = temp_path / output_filename
        schema_path.write_text(json.dumps(schema), encoding="utf-8")
        command = [
            executable, "exec", "--ephemeral", "--sandbox", "read-only", "--skip-git-repo-check",
            "--cd", str(temp_path), "--output-schema", str(schema_path),
        ]
        for image_path in image_paths:
            command.extend(["--image", str(image_path)])
        command.extend(["--output-last-message", str(output_path), "-"])
        try:
            result = subprocess.run(command, input=prompt, text=True, capture_output=True, timeout=180)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("Codex CLI timed out after 180 seconds") from error
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip()[-1200:]
            raise RuntimeError(f"Codex CLI exited with status {result.returncode}: {detail}")
        if not output_path.is_file():
            raise RuntimeError("Codex CLI finished without writing its structured response")
        content = output_path.read_text(encoding="utf-8").strip()
        if not content:
            raise ValueError("Codex CLI returned an empty draft")
        return draft_type.model_validate_json(content), model
