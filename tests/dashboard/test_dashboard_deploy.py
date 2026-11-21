"""Run the real deployment script over stdin with isolated command stubs."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(os.name == 'posix', 'Deployment runs on Linux')
class DashboardDeployTest(unittest.TestCase):
    def test_piped_deploy_keeps_stdin_and_backups_in_the_deploy_users_state_directory(self):
        script = Path(__file__).resolve().parents[2] / 'scripts/deploy/deploy.sh'
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('bin', 'checkout', 'home', 'state'):
                (root / name).mkdir()
            stub = r'''
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
args=sys.argv[1:]
if name=='git':
    if args[:1]==['rev-parse']: print('same')
    elif args[:1]==['log']: print('same release')
elif name=='curl': print('401' if args[-1].endswith('/api/auth/me') else '200')
elif name=='docker':
    if args[:2]==['compose','ps']: print('container')
    elif args[:1]==['inspect']: print('true')
    elif args[:2]==['compose','exec']:
        consumed=sys.stdin.read()
        path=Path(os.environ['DEPLOY_TEST_LOG'])
        with path.open('a') as out: out.write(json.dumps({'consumed_stdin':bool(consumed)})+'\n')
        count=len(path.read_text().splitlines())
        print('backup' if count==1 else 'migrated' if count==2 else 'Shared dashboard storage is ready')
'''
            for name in ('git', 'docker', 'curl'):
                path = root / 'bin' / name
                path.write_text('#!' + sys.executable + '\n' + stub)
                path.chmod(0o755)
            env = {**os.environ, 'PATH': str(root / 'bin') + os.pathsep + os.environ['PATH'],
                   'HOME': str(root / 'home'), 'XDG_STATE_HOME': str(root / 'state'),
                   'DEPLOY_DIR': str(root / 'checkout'), 'DEPLOY_TEST_LOG': str(root / 'commands.jsonl')}
            result = subprocess.run(['bash', '-s'], input=script.read_bytes(), env=env, capture_output=True, timeout=10)
            self.assertEqual(0, result.returncode, result.stderr.decode())
            calls = [json.loads(line) for line in (root / 'commands.jsonl').read_text().splitlines()]
            self.assertEqual(3, len(calls), result.stdout.decode())
            self.assertFalse(any(call['consumed_stdin'] for call in calls))
            self.assertIn('Deployed same release', result.stdout.decode())
            backups = list((root / 'state').rglob('*.sqlite3'))
            self.assertEqual(1, len(backups))
            self.assertEqual(0o600, backups[0].stat().st_mode & 0o777)
