"""Isolated Hugging Face Transformers worker for Vintern invoice extraction."""

from __future__ import annotations

import json
from pathlib import Path
import sys


def _dynamic_preprocess(image, image_size: int = 448, max_num: int = 12):
    aspect_ratio = image.width / image.height
    ratios = sorted({
        (width, height)
        for count in range(1, max_num + 1)
        for width in range(1, count + 1)
        for height in range(1, count + 1)
        if 1 <= width * height <= max_num
    }, key=lambda ratio: ratio[0] * ratio[1])
    target = (1, 1)
    best_difference = float("inf")
    image_area = image.width * image.height
    for ratio in ratios:
        difference = abs(aspect_ratio - ratio[0] / ratio[1])
        if difference < best_difference:
            best_difference = difference
            target = ratio
        elif difference == best_difference and image_area > 0.5 * image_size**2 * ratio[0] * ratio[1]:
            target = ratio
    width, height = image_size * target[0], image_size * target[1]
    resized = image.resize((width, height))
    crops = [
        resized.crop((x * image_size, y * image_size, (x + 1) * image_size, (y + 1) * image_size))
        for y in range(height // image_size)
        for x in range(width // image_size)
    ]
    if len(crops) > 1:
        crops.append(image.resize((image_size, image_size)))
    return crops


def _allow_optional_flash_attn_import() -> None:
    """Let Vintern's guarded Flash Attention import use its built-in fallback."""
    import transformers.dynamic_module_utils as dynamic_module_utils

    check_imports = dynamic_module_utils.check_imports

    def check_model_imports(filename):
        try:
            return check_imports(filename)
        except ImportError as error:
            source_path = Path(filename)
            source = source_path.read_text(encoding="utf-8")
            optional_flash_attn = (
                source_path.name == "modeling_intern_vit.py"
                and "flash_attn" in str(error)
                and "has_flash_attn = False" in source
            )
            if not optional_flash_attn:
                raise
            return dynamic_module_utils.get_relative_imports(filename)

    dynamic_module_utils.check_imports = check_model_imports


def _chat_on_device(model, tokenizer, pixel_values, question, generation_config, device):
    """Run Vintern chat without its upstream hard-coded CUDA tensor moves."""
    template = model.conv_template.copy()
    template.system_message = model.system_message
    img_context_token = "<IMG_CONTEXT>"
    model.img_context_token_id = tokenizer.convert_tokens_to_ids(img_context_token)
    question = f"<image>\n{question}"
    image_tokens = (
        "<img>" + img_context_token * model.num_image_token * pixel_values.shape[0] + "</img>"
    )
    template.append_message(template.roles[0], question)
    template.append_message(template.roles[1], None)
    query = template.get_prompt().replace("<image>", image_tokens, 1)
    model_inputs = tokenizer(query, return_tensors="pt")
    eos_token_id = tokenizer.convert_tokens_to_ids(template.sep)
    generation_config["eos_token_id"] = eos_token_id
    language_model = model.language_model
    original_generate = language_model.generate

    def generate_without_return_dict(*args, **kwargs):
        # The pinned upstream wrapper passes return_dict through as an unknown
        # generation kwarg; Transformers then duplicates it in model.forward.
        kwargs.pop("return_dict", None)
        return original_generate(*args, **kwargs)

    language_model.generate = generate_without_return_dict
    try:
        generated = model.generate(
            pixel_values=pixel_values,
            input_ids=model_inputs["input_ids"].to(device),
            attention_mask=model_inputs["attention_mask"].to(device),
            **generation_config,
        )
    finally:
        language_model.generate = original_generate
    response = tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
    return response.split(template.sep)[0].strip()


def run(request_path: Path, response_path: Path) -> None:
    import torch
    import torchvision.transforms as transforms
    from PIL import Image
    from torchvision.transforms.functional import InterpolationMode
    from transformers import AutoModel, AutoTokenizer

    request = json.loads(request_path.read_text(encoding="utf-8"))
    requested_device = str(request.get("device", "cpu")).lower()
    if requested_device.startswith("cuda"):
        if not torch.cuda.is_available():
            raise RuntimeError("CUDA was selected for Vintern, but CUDA is unavailable in its runtime.")
        device = "cuda"
        dtype = torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16
    else:
        device = "cpu"
        # Keep the 1B model's resident weights small enough for a CPU-only laptop.
        dtype = torch.float16

    model_id = request["model_id"]
    revision = request.get("revision")
    _allow_optional_flash_attn_import()
    tokenizer = AutoTokenizer.from_pretrained(
        model_id, trust_remote_code=True, use_fast=False, revision=revision
    )
    model = AutoModel.from_pretrained(
        model_id,
        revision=revision,
        code_revision=revision,
        torch_dtype=dtype,
        low_cpu_mem_usage=True,
        trust_remote_code=True,
    ).eval().to(device)
    transform = transforms.Compose([
        transforms.Lambda(lambda image: image.convert("RGB")),
        transforms.Resize((448, 448), interpolation=InterpolationMode.BICUBIC),
        transforms.ToTensor(),
        transforms.Normalize(
            mean=(0.485, 0.456, 0.406),
            std=(0.229, 0.224, 0.225),
        ),
    ])

    pages = []
    for page in request["pages"]:
        with Image.open(page["image_path"]) as image:
            crops = _dynamic_preprocess(image.convert("RGB"))
            pixel_values = torch.stack([transform(crop) for crop in crops]).to(
                device=device, dtype=dtype
            )
        response = _chat_on_device(
            model,
            tokenizer,
            pixel_values,
            request["prompt"],
            {
                "max_new_tokens": 1024,
                "do_sample": False,
                "num_beams": 3,
                "repetition_penalty": 2.0,
            },
            device,
        )
        pages.append({"page_number": page["page_number"], "response": str(response)})

    response_path.write_text(
        json.dumps(
            {"model_id": model_id, "revision": revision, "pages": pages},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: python -m document_processing.receipt.vintern_worker REQUEST.json RESPONSE.json")
    run(Path(sys.argv[1]), Path(sys.argv[2]))
