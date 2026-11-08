"""Isolated worker for the text-only Qwen invoice extractor."""

from __future__ import annotations

import json
import os
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
    adapter_id = str(request.get("adapter_id") or "").strip() or None
    adapter_revision = str(request.get("adapter_revision") or "main")
    hf_token = os.environ.get("HF_INVOICE_LLM_TOKEN")
    if adapter_id and not hf_token:
        raise RuntimeError(
            "HF_INVOICE_LLM_TOKEN is required to load the private invoice LoRA adapter"
        )
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model_dtype = torch.float16 if device.type == "cuda" else torch.float32

    load_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(model_id, revision=revision, token=hf_token)
    model = AutoModelForCausalLM.from_pretrained(
        model_id,
        revision=revision,
        torch_dtype=model_dtype,
        low_cpu_mem_usage=True,
        token=hf_token,
    )
    if adapter_id:
        from peft import PeftModel

        model = PeftModel.from_pretrained(
            model,
            adapter_id,
            revision=adapter_revision,
            token=hf_token,
        )
    model = model.to(device).eval()
    load_seconds = time.perf_counter() - load_start
    if device.type == "cuda":
        torch.cuda.reset_peak_memory_stats(device)

    jobs = request.get("jobs") or [{
        "source": "document", "prompt": request.get("prompt", ""),
        "max_new_tokens": request.get("max_new_tokens", 384),
    }]
    responses = []
    prompt_tokens = generated_tokens = 0
    inference_seconds = 0.0
    for job in jobs:
        template_options = {"add_generation_prompt": True, "tokenize": False}
        if model_id.startswith("Qwen/Qwen3"):
            template_options["enable_thinking"] = False
        prompt = tokenizer.apply_chat_template(
            [{"role": "user", "content": job["prompt"]}],
            **template_options,
        )
        inputs = tokenizer(prompt, return_tensors="pt")
        if inputs["input_ids"].shape[-1] > 32_000:
            raise ValueError(
                f"Invoice OCR chunk {job.get('source', '')} exceeds the model's 32K token context"
            )
        inputs = {key: value.to(device) for key, value in inputs.items()}

        infer_start = time.perf_counter()
        with torch.inference_mode():
            output = model.generate(
                **inputs,
                max_new_tokens=int(job.get("max_new_tokens", 1024)),
                do_sample=False,
                pad_token_id=tokenizer.eos_token_id,
            )
        if device.type == "cuda":
            torch.cuda.synchronize(device)
        inference_seconds += time.perf_counter() - infer_start
        prompt_length = inputs["input_ids"].shape[-1]
        prompt_tokens += int(prompt_length)
        generated_tokens += int(output.shape[-1] - prompt_length)
        responses.append(tokenizer.decode(
            output[0][prompt_length:], skip_special_tokens=True,
        ).strip())
    result = {
        "revision": revision,
        "adapter": adapter_id,
        "adapter_revision": adapter_revision if adapter_id else None,
        "responses": responses,
        "metrics": {
            "device": str(device),
            "dtype": str(model_dtype),
            "load_seconds": round(load_seconds, 2),
            "inference_seconds": round(inference_seconds, 2),
            "prompt_tokens": prompt_tokens,
            "generated_tokens": generated_tokens,
            "peak_process_ram_mib": round(
                resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1,
            ),
            "peak_gpu_memory_mib": round(
                torch.cuda.max_memory_allocated(device) / 1024**2, 1,
            ) if device.type == "cuda" else 0,
        },
    }
    response_path.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
