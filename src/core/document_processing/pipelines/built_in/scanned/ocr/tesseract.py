"""Small shared runner for direct Tesseract OCR calls."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

_BOOLEAN_OPTIONS = (
    "preserve_interword_spaces",
    "load_system_dawg",
    "load_freq_dawg",
    "tessedit_do_invert",
    "textord_tablefind_recognize_tables",
    "textord_tabfind_find_tables",
    "lstm_use_matrix",
)
_NUMERIC_OPTIONS = {
    "thresholding_method": {0, 1, 2},
    "lstm_rating_coefficient": {3, 5, 7},
}


def _config_args(config: dict[str, Any]) -> list[str]:
    settings = config.get("tesseract_config", {})
    args = []
    for name in _BOOLEAN_OPTIONS:
        if name in settings:
            args.extend(["-c", f"{name}={int(bool(settings[name]))}"])
    for name, allowed_values in _NUMERIC_OPTIONS.items():
        if name in settings:
            value = int(settings[name])
            if value not in allowed_values:
                raise ValueError(f"Unsupported Tesseract setting: {name}={value}")
            args.extend(["-c", f"{name}={value}"])
    return args


def run_tesseract(
    image_bytes: bytes,
    config: dict[str, Any],
    *,
    language: str | None = None,
    page_segmentation_mode: int = 11,
    timeout: int = 90,
    output_format: str | None = None,
    tessdata_dir: Path | None = None,
    include_config: bool = True,
) -> str:
    """Run Tesseract against image bytes and return decoded stdout."""
    command = [
        "tesseract", "stdin", "stdout", "-l",
        language or config.get("ocr_language", "vie+eng"),
        "--psm", str(page_segmentation_mode),
    ]
    if tessdata_dir is not None:
        command.extend(["--tessdata-dir", str(tessdata_dir)])
    if include_config:
        command.extend(_config_args(config))
    if output_format:
        command.append(output_format)
    result = subprocess.run(
        command, input=image_bytes, capture_output=True, check=True, timeout=timeout,
    )
    return result.stdout.decode("utf-8", errors="replace")
