"""GPU-backed Modal endpoint for the private Qwen3 invoice LoRA adapter.

Deploy from the repository root with:
    modal deploy src/document_processing/modal_invoice_endpoint.py

The Modal Secret ``invoice-hf-token`` must contain ``HF_INVOICE_LLM_TOKEN``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from typing import Any

import modal


MODEL_ID = "Qwen/Qwen3-0.6B"
MODEL_REVISION = "c1899de289a04d12100db370d81485cdf75e47ca"
ADAPTER_ID = "lenhanm1/qwen3-0.6b-invoice-lora-900"
ADAPTER_REVISION = "7e062bb552f77af64b1c3bc9e205fa107c68c3d3"

app = modal.App("enterprise-invoice-qwen3-lora")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .pip_install(
        "fastapi[standard]",
        "torch==2.3.1",
        "transformers==4.57.6",
        "accelerate==1.15.0",
        "peft==0.21.2",
        "sentencepiece",
    )
    .add_local_dir("src/document_processing", remote_path="/root/document_processing")
)


@app.cls(
    image=image,
    gpu=["L4", "A10"],
    secrets=[modal.Secret.from_name("invoice-hf-token")],
    scaledown_window=300,
    timeout=1800,
    max_containers=3,
)
class InvoiceQwenGPU:
    @modal.enter()
    def load_model(self) -> None:
        sys.path.insert(0, "/root")
        from document_processing.invoice_text_worker import InvoiceModelRuntime

        request = {
            "model_id": MODEL_ID,
            "revision": MODEL_REVISION,
            "adapter_id": ADAPTER_ID,
            "adapter_revision": ADAPTER_REVISION,
        }
        self.runtime = InvoiceModelRuntime(request, device="cuda")

    @modal.fastapi_endpoint(method="POST")
    def extract(self, payload: dict[str, Any]) -> dict[str, Any]:
        token = os.environ.get("HF_INVOICE_LLM_TOKEN", "")
        if not token:
            raise RuntimeError("HF_INVOICE_LLM_TOKEN is missing from Modal Secret invoice-hf-token")

        signature = str(payload.pop("auth_signature", ""))
        canonical = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        expected = hmac.new(token.encode("utf-8"), canonical, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise PermissionError("Invalid invoice endpoint signature")
        return self.runtime.infer(payload)
