"""Run the existing frozen harness against production or the isolated patched checkout."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

from dotenv import load_dotenv


def main():
    root=Path(__file__).resolve().parents[1]
    if len(sys.argv)<3 or sys.argv[1] not in {'production','single-pass','single-pass-v2'}:
        raise SystemExit('Usage: python evaluation/run_sql_single_pass_benchmark.py production|single-pass|single-pass-v2 --stage verify|generate|score')
    mode=sys.argv.pop(1)
    work=root if mode=='production' else root/('artifacts/local/sql-single-pass-variant' if mode=='single-pass' else 'artifacts/local/sql-single-pass-candidate')
    load_dotenv(root/'.env')
    os.chdir(work)
    sys.path[:0]=[str(work),str(work/'src')]
    from evaluation import run_sql_contract_benchmark as runner
    runner.FROZEN=root/'artifacts/evaluation/agent-benchmarks-2026-11-02'
    output=root/'artifacts/evaluation/sql-single-pass-2026-11-04'/mode
    original=runner.prepare
    def prepare(**kwargs):
        original(**kwargs)
        manifest=json.loads((runner.OUTPUT/'manifest.json').read_text(encoding='utf-8'))
        hashes={name:hashlib.sha256((root/'evaluation'/name).read_bytes()).hexdigest()
                for name in ['sql_single_pass.patch','sql_single_pass_contract.py','run_sql_single_pass_benchmark.py']}
        assert not manifest.get('evaluation_source_sha256') or manifest['evaluation_source_sha256']==hashes,'Experiment implementation changed'
        manifest.update(experiment='isolated single-pass vs unchanged production',variant=mode,
            production_base='f48bec538f4cabac148cf75e9593f282d376a328',
            evaluation_source_sha256=hashes)
        runner.benchmark.save(runner.OUTPUT/'manifest.json',manifest)
    runner.prepare=prepare
    if mode=='production':
        assert subprocess.run(['git','diff','--quiet','f48bec5','--','src'],cwd=root).returncode==0,'Production source changed'
    else:
        assert (work/'evaluation/sql_single_pass_contract.py').read_bytes()==(root/'evaluation/sql_single_pass_contract.py').read_bytes(),'Variant contract differs'
        assert subprocess.check_output(['git','diff','f48bec5','--','src'],cwd=work)==(root/'evaluation/sql_single_pass.patch').read_bytes(),'Variant source differs from the reviewed patch'
    sys.argv.extend(['--group','sql_analytics','--retry-provider-errors'])
    if '--output' not in sys.argv:
        sys.argv.extend(['--output',str(output)])
    asyncio.run(runner.main())


if __name__=='__main__':
    main()
