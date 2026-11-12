import os, runpy
from pathlib import Path
os.environ['END_TO_END_PIPELINE'] = 'docling'
matches = list(Path('/kaggle/input').rglob('run_end_to_end_kaggle.py'))
if len(matches) != 1:
    raise RuntimeError(f'Expected one shared runner, found {matches}')
runpy.run_path(str(matches[0]), run_name='__main__')
