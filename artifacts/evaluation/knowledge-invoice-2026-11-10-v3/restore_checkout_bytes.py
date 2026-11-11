"""Restore ONLY verified LF/CRLF forms in a fresh pinned reproduction checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--checkout',type=Path,required=True)
parser.add_argument('--write',action='store_true',help='Without this flag only report required newline restorations')
args=parser.parse_args()
root=args.checkout.resolve()
manifest=json.loads(Path(__file__).with_name('manifest.json').read_text(encoding='utf-8'))
revision=manifest['application_revision']
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==revision, 'Use a fresh worktree at the measured revision'
expected={**manifest['source_hashes'],**manifest['preserved_history']}
changed=[]
for name,checksum in expected.items():
    relative=name.replace('\\','/')
    path=(root/relative).resolve()
    assert path.is_relative_to(root), 'Manifest path escaped checkout'
    if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest()==checksum:
        continue
    blob=subprocess.check_output(['git','show',f'{revision}:{relative}'],cwd=root)
    candidates=[blob,blob.replace(b'\r\n',b'\n'),blob.replace(b'\r\n',b'\n').replace(b'\n',b'\r\n')]
    match=next((data for data in candidates if hashlib.sha256(data).hexdigest()==checksum),None)
    assert match is not None, f'Not a verified newline-only difference: {name}'
    if args.write:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(match)
    changed.append(relative)
print(json.dumps(dict(verified_files=len(expected),newline_restorations=changed,written=args.write),indent=2))
