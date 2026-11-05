"""Isolated CPU worker for the text-only Qwen invoice extractor."""

from __future__ import annotations

import json
import resource
from pathlib import Path
import sys
import time


def run(request_path: Path, response_path: Path) -> None:
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    request = json.loads(request_path.read_text(encoding="utf-8"))
    torch.set_num_threads(max(1, min(8, int(request.get("cpu_threads", 2)))))
    model_id = str(request["model_id"])
    revision = str(request["revision"])

    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=torch.float32,
        low_cpu_mem_usage=True,
    ).eval()
    load_seconds = time.perf_counter() - load_start

    prompt = tokenizer.apply_chat_template(
        [{"role": "user", "content": request["prompt"]}],
        add_generation_prompt=True,
        tokenize=False,
    )
    inputs = tokenizer(prompt, return_tensors="pt")
    if inputs["input_ids"].shape[-1] > 32_000:
        raise ValueError("Invoice OCR text exceeds the model's 32K token context")

    infer_start = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=384,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )
    inference_seconds = time.perf_counter() - infer_start
    response = tokenizer.decode(
        output[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True,
    ).strip()
    result = {
        "revision": revision,
        "response": response,
        "metrics": {
            "load_seconds": round(load_seconds, 2),
            "inference_seconds": round(inference_seconds, 2),
            "prompt_tokens": int(inputs["input_ids"].shape[-1]),
            "generated_tokens": int(output.shape[-1] - inputs["input_ids"].shape[-1]),
            "peak_process_ram_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1,
            ),
        },
    }
    response_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
