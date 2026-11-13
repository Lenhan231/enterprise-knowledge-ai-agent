"""Isolated worker and reusable runtime for the text-only Qwen invoice extractor."""

from __future__ import annotations

import json
import os
import resource
from pathlib import Path
import sys
import time
from typing import Any


class InvoiceModelRuntime:
    """Load Qwen and its adapter once, then reuse them for extraction jobs."""

    def __init__(self, request: dict[str, Any], *, device: str | None = None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.torch = torch
        self.model_id = str(request["model_id"])
        self.revision = str(request["revision"])
        self.adapter_id = str(request.get("adapter_id") or "").strip() or None
        self.adapter_revision = str(request.get("adapter_revision") or "main")
        token = os.environ.get("HF_INVOICE_LLM_TOKEN")
        if self.adapter_id and not token:
            raise RuntimeError(
                "HF_INVOICE_LLM_TOKEN is required to load the private invoice LoRA adapter"
            )

        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self.model_dtype = torch.float16 if self.device.type == "cuda" else torch.float32
        started = time.perf_counter()
        self.tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, revision=self.revision, token=token,
        )
        self.tokenizer.padding_side = "left"
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        model = AutoModelForCausalLM.from_pretrained(
            self.model_id,
            revision=self.revision,
            torch_dtype=self.model_dtype,
            low_cpu_mem_usage=True,
            token=token,
        )
        if self.adapter_id:
            from peft import PeftModel

            model = PeftModel.from_pretrained(
                model,
                self.adapter_id,
                revision=self.adapter_revision,
                token=token,
            )
        self.model = model.to(self.device).eval()
        self.load_seconds = time.perf_counter() - started
        if self.device.type == "cuda":
            torch.cuda.reset_peak_memory_stats(self.device)

    def infer(self, request: dict[str, Any]) -> dict[str, Any]:
        if str(request.get("model_id")) != self.model_id or str(request.get("revision")) != self.revision:
            raise ValueError("Invoice request base model does not match the loaded model")
        if (str(request.get("adapter_id") or "").strip() or None) != self.adapter_id:
            raise ValueError("Invoice request adapter does not match the loaded adapter")
        if self.adapter_id and str(request.get("adapter_revision") or "main") != self.adapter_revision:
            raise ValueError("Invoice request adapter revision does not match the loaded adapter")

        torch = self.torch
        jobs = request.get("jobs") or [{
            "source": "document", "prompt": request.get("prompt", ""),
            "max_new_tokens": request.get("max_new_tokens", 384),
        }]
        responses: list[str] = []
        prompt_tokens = generated_tokens = 0
        inference_seconds = 0.0
        batch_size = 4
        for offset in range(0, len(jobs), batch_size):
            batch = jobs[offset:offset + batch_size]
            prompts = []
            for job in batch:
                template_options = {"add_generation_prompt": True, "tokenize": False}
                if self.model_id.startswith("Qwen/Qwen3"):
                    template_options["enable_thinking"] = False
                prompts.append(self.tokenizer.apply_chat_template(
                    [{"role": "user", "content": job["prompt"]}],
                    **template_options,
                ))
            inputs = self.tokenizer(prompts, padding=True, return_tensors="pt")
            lengths = inputs["attention_mask"].sum(dim=-1)
            if int(lengths.max()) > 32_000:
                source = batch[int(lengths.argmax())].get("source", "")
                raise ValueError(
                    f"Invoice OCR chunk {source} exceeds the model's 32K token context"
                )
            inputs = {key: value.to(self.device) for key, value in inputs.items()}

            infer_start = time.perf_counter()
            with torch.inference_mode():
                output = self.model.generate(
                    **inputs,
                    max_new_tokens=max(int(job.get("max_new_tokens", 1024)) for job in batch),
                    do_sample=False,
                    pad_token_id=self.tokenizer.pad_token_id,
                )
            if self.device.type == "cuda":
                torch.cuda.synchronize(self.device)
            inference_seconds += time.perf_counter() - infer_start
            input_width = inputs["input_ids"].shape[-1]
            prompt_tokens += int(lengths.sum().item())
            for index, job in enumerate(batch):
                generated = output[index, input_width:]
                token_limit = int(job.get("max_new_tokens", 1024))
                generated = generated[:token_limit]
                generated_tokens += int(generated.shape[-1])
                responses.append(self.tokenizer.decode(
                    generated, skip_special_tokens=True,
                ).strip())

        return {
            "revision": self.revision,
            "adapter": self.adapter_id,
            "adapter_revision": self.adapter_revision if self.adapter_id else None,
            "responses": responses,
            "metrics": {
                "device": str(self.device),
                "dtype": str(self.model_dtype),
                "load_seconds": round(self.load_seconds, 2),
                "inference_seconds": round(inference_seconds, 2),
                "prompt_tokens": prompt_tokens,
                "generated_tokens": generated_tokens,
                "peak_process_ram_mib": round(
                    resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1,
                ),
                "peak_gpu_memory_mib": round(
                    torch.cuda.max_memory_allocated(self.device) / 1024**2, 1,
                ) if self.device.type == "cuda" else 0,
            },
        }


def run(request_path: Path, response_path: Path) -> None:
    request = json.loads(request_path.read_text(encoding="utf-8"))
    import torch

    torch.set_num_threads(max(1, min(8, int(request.get("cpu_threads", 2)))))
    response = InvoiceModelRuntime(request).infer(request)
    response_path.write_text(json.dumps(response, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    run(Path(sys.argv[1]), Path(sys.argv[2]))
