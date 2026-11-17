"""Isolated Transformers worker for Xiaomi-OCR-0 invoice extraction."""

from __future__ import annotations

import json
from pathlib import Path
import resource
import sys
import time


def run(request_path: Path, response_path: Path) -> None:
    import torch
    from PIL import Image
    from transformers import AutoModelForImageTextToText, AutoProcessor

    request = json.loads(request_path.read_text(encoding="utf-8"))
    torch.set_num_threads(max(1, min(8, int(request.get("cpu_threads", 2)))))
    requested_device = str(request.get("device", "auto")).lower()
    if requested_device == "auto":
        device = "cuda" if torch.cuda.is_available() else "cpu"
    elif requested_device.startswith("cuda") and not torch.cuda.is_available():
        raise RuntimeError("CUDA was selected for Xiaomi-OCR-0, but CUDA is unavailable")
    else:
        device = requested_device
    dtype = torch.float16 if device.startswith("cuda") else torch.float32

    model_id = request["model_id"]
    revision = request.get("revision") or "main"
    started = time.perf_counter()
    processor = AutoProcessor.from_pretrained(model_id, revision=revision)
    model = AutoModelForImageTextToText.from_pretrained(
        model_id,
        revision=revision,
        dtype=dtype,
        low_cpu_mem_usage=True,
    ).to(device).eval()
    load_seconds = time.perf_counter() - started
    if device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats(device)

    pages = []
    inference_seconds = 0.0
    prompt_tokens = generated_tokens = 0
    for page in request["pages"]:
        with Image.open(page["image_path"]) as source:
            image = source.convert("RGB")
        messages = [{
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": request["prompt"]},
            ],
        }]
        inputs = processor.apply_chat_template(
            messages,
            tokenize=True,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(model.device)
        prompt_tokens += int(inputs["input_ids"].shape[-1])
        stage_started = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=int(request.get("max_new_tokens", 4096)),
                do_sample=False,
            )
        if device.startswith("cuda"):
            torch.cuda.synchronize(device)
        inference_seconds += time.perf_counter() - stage_started
        new_tokens = output[0, inputs["input_ids"].shape[-1]:]
        generated_tokens += int(new_tokens.shape[-1])
        pages.append({
            "page_number": page["page_number"],
            "response": processor.decode(new_tokens, skip_special_tokens=True).strip(),
        })

    response_path.write_text(json.dumps({
        "model_id": model_id,
        "revision": getattr(model.config, "_commit_hash", None) or revision,
        "pages": pages,
        "metrics": {
            "device": str(device),
            "dtype": str(dtype),
            "load_seconds": round(load_seconds, 2),
            "inference_seconds": round(inference_seconds, 2),
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "peak_process_ram_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
            "peak_gpu_memory_mib": round(torch.cuda.max_memory_allocated(device) / 1024**2, 1)
            if device.startswith("cuda") else 0,
        },
    }, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m document_processing.xiaomi_ocr_worker REQUEST.json RESPONSE.json")
    run(Path(sys.argv[1]), Path(sys.argv[2]))
