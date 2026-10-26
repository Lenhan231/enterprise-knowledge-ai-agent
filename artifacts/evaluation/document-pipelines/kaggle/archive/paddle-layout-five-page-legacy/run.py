import json
import os
import subprocess
import sys
import time
from pathlib import Path

import torch
from PIL import Image

input_root = Path('/kaggle/input')
manifest_paths = list(input_root.rglob('shared-html-reviewed-pages.jsonl'))
if len(manifest_paths) != 1:
    raise RuntimeError(f'Expected one reviewed-pages manifest, found {manifest_paths}')
manifest_path = manifest_paths[0]
input_root = manifest_path.parent
manifest = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
page_ids = {
    'E2E-LONG-HAU-2008-p6',
    'E2E-LONG-HAU-2008-p8',
    'E2E-LONG-HAU-2008-p17',
    'E2E-BAO-HO-LAO-DONG-2009-p13',
    'E2E-BAO-HO-LAO-DONG-2009-p24',
}
pages = [row for row in manifest if row['reference_id'] in page_ids]
if {row['reference_id'] for row in pages} != page_ids:
    raise RuntimeError('The Kaggle input does not contain all five pilot pages')
if not torch.cuda.is_available():
    raise RuntimeError('Kaggle did not allocate a GPU')

print('GPU:', torch.cuda.get_device_name(0), flush=True)
print('CUDA:', torch.version.cuda, flush=True)
subprocess.run([
    sys.executable, '-m', 'pip', 'install', '-q',
    'paddlepaddle-gpu==3.2.1',
    '--extra-index-url', 'https://www.paddlepaddle.org.cn/packages/stable/cu126/',
], check=True)
subprocess.run([
    sys.executable, '-m', 'pip', 'install', '-q',
    'paddleocr==3.5.0',
    'langchain-text-splitters',
], check=True)

os.environ.setdefault('PADDLE_PDX_MODEL_SOURCE', 'BOS')
import paddle
from paddleocr import LayoutDetection

if not paddle.is_compiled_with_cuda():
    raise RuntimeError('Installed PaddlePaddle build has no CUDA support')
paddle.device.set_device('gpu:0')
model = LayoutDetection(model_name='PP-DocLayout-S', device='gpu:0')
output_path = Path('/kaggle/working/paddle-layout-predictions.jsonl')
timings = {}
seal_counts = {}
with output_path.open('w') as out:
    for row in pages:
        page_id = row['reference_id']
        image_path = input_root / row['image_file']
        with Image.open(image_path) as image:
            width, height = image.size
        started = time.perf_counter()
        results = model.predict(str(image_path), batch_size=1, layout_nms=True)
        result = next(iter(results))
        payload = result.json
        if isinstance(payload, str):
            payload = json.loads(payload)
        raw = payload.get('res', payload)
        boxes = raw.get('boxes', [])
        record = {
            'reference_id': page_id,
            'document_id': row['document_id'],
            'source_page_number_1based': row['source_page_number_1based'],
            'image_file': row['image_file'],
            'width': width,
            'height': height,
            'boxes': boxes,
        }
        out.write(json.dumps(record, ensure_ascii=False) + '\n')
        timings[page_id] = round(time.perf_counter() - started, 3)
        seal_counts[page_id] = sum(box.get('label') == 'seal' for box in boxes)
        print(page_id, 'regions=', len(boxes), 'seals=', seal_counts[page_id], flush=True)

metadata = {
    'model': 'PP-DocLayout-S',
    'engine': 'PaddleOCR LayoutDetection / Paddle Inference',
    'device': paddle.device.get_device(),
    'page_count': len(pages),
    'page_seconds': timings,
    'seal_counts': seal_counts,
}
Path('/kaggle/working/paddle-layout-metadata.json').write_text(json.dumps(metadata, indent=2))
print('Wrote', output_path, flush=True)
