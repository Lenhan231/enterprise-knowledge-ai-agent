"""Two disjoint scoring partitions of ONE frozen cohort; never blend runs.

Run prepare-a / score-a, then prepare-b / score-b once its generations exist,
then merge. Each worker keeps its raw records and its own Codex schema directory.
"""
import json
import importlib.metadata
from pathlib import Path
import runpy
import shutil
import sys
import tempfile

COHORT = Path(__file__).resolve().parent
ROOT = COHORT.parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / 'src')]
from evaluation.run_knowledge_invoice_benchmark import verify, digest, immutable_json, append_once, read_jsonl

PARTITIONS = {'a': [f'K{i:02}' for i in range(2, 16)],
              'b': [f'K{i:02}' for i in range(16, 31) if i != 26]}
assert not set(PARTITIONS['a']) & set(PARTITIONS['b'])
assert set(sum(PARTITIONS.values(), [])) | {'K01', 'K26'} == {f'K{i:02}' for i in range(1, 31)}


def checked_manifest(folder):
    manifest = verify(folder)
    assert {name: importlib.metadata.version(name) for name in manifest['packages']} == manifest['packages'], 'Package versions changed'
    return manifest


def prepare(name):
    manifest = checked_manifest(COHORT)
    worker = COHORT / f'scoring-worker-{name}'
    records = [r for r in read_jsonl(COHORT / 'knowledge/generations.jsonl') if r['id'] in PARTITIONS[name]]
    assert {r['id'] for r in records} == set(PARTITIONS[name]), 'Wait for missing generations'
    worker.mkdir(exist_ok=True)
    for file in ('manifest.json', 'cases.json', 'database-before.json'):
        destination = worker / file
        if destination.exists():
            assert destination.read_bytes() == (COHORT / file).read_bytes()
        else:
            shutil.copyfile(COHORT / file, destination)
    immutable_json(worker / 'partition.json', dict(ids=PARTITIONS[name], config=manifest['config'],
        parent_manifest_sha256=digest((COHORT / 'manifest.json').read_bytes()),
        generation_hashes={r['id']: digest(r) for r in records}))
    existing = read_jsonl(worker / 'knowledge/generations.jsonl')
    for row in records:
        saved = [r for r in existing if r['id'] == row['id']]
        if saved:
            assert saved == [row]
        else:
            append_once(worker / 'knowledge/generations.jsonl', row, ('id',))
    checked_manifest(worker)


def merge():
    checked_manifest(COHORT)
    generations = {r['id']: digest(r) for r in read_jsonl(COHORT / 'knowledge/generations.jsonl')}
    existing = {(r['id'], r['metric']):r for r in read_jsonl(COHORT / 'knowledge/scores.jsonl')}
    for name, ids in PARTITIONS.items():
        worker = COHORT / f'scoring-worker-{name}'
        checked_manifest(worker)
        partition = json.loads((worker / 'partition.json').read_text(encoding='utf-8'))
        assert partition['parent_manifest_sha256'] == digest((COHORT / 'manifest.json').read_bytes())
        records = read_jsonl(worker / 'knowledge/scores.jsonl')
        expected = {(identifier, metric) for identifier in ids for metric in
                    ['faithfulness','answer_relevancy','context_precision']}
        assert len(records) == len(expected) and {(r['id'],r['metric']) for r in records} == expected
        for row in records:
            assert row['generation_sha256'] == generations[row['id']] == partition['generation_hashes'][row['id']]
            key = row['id'],row['metric']
            if key in existing:
                assert row == existing[key], 'Never replace a score, including a failure'
            else:
                append_once(COHORT / 'knowledge/scores.jsonl',row,('id','metric'))
    print('Merged identical-source/dataset/config, disjoint metric partitions; raw worker files retained.')


if __name__ == '__main__':
    action = sys.argv[1]
    if action == 'merge':
        merge()
    elif action.startswith('prepare-'):
        prepare(action[-1])
    else:
        assert action in {'score-a','score-b'}
        name = action[-1]
        worker = COHORT / f'scoring-worker-{name}'
        checked_manifest(worker)
        temp = worker / '.judge-tmp'
        temp.mkdir(exist_ok=True)
        tempfile.tempdir = str(temp)
        sys.argv = ['benchmark','--stage','score','--group','knowledge','--output',str(worker),
                    '--env-file',str(ROOT.parents[2] / '.env')]
        runpy.run_module('evaluation.run_knowledge_invoice_benchmark',run_name='__main__')
