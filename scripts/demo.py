"""Exercise the public CLI using temporary synthetic data, without a model."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/not_yet_dead.py'


def cli(*arguments):
    call = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, arguments)],
                          capture_output=True, text=True, encoding='utf-8', timeout=20)
    if call.returncode:
        raise RuntimeError(call.stderr)
    return json.loads(call.stdout)


def file_bytes(root):
    return {p.relative_to(root).as_posix(): p.read_bytes()
            for p in root.rglob('*') if p.is_file()}


def main():
    original_examples = file_bytes(ROOT / 'examples')
    doctor = cli('doctor')
    with tempfile.TemporaryDirectory(prefix='not-yet-dead-demo-') as directory:
        root = Path(directory)
        work = root / 'workspace'
        shutil.copytree(ROOT / 'examples/workspace', work)
        bundle = root / 'handoff'
        cli('extract', '--snapshot', ROOT / 'examples/snapshot.json',
            '--checkpoint', ROOT / 'examples/checkpoint.json',
            '--workspace', work, '--out', bundle)
        manifest = cli('verify', bundle)
        before = cli('resume', '--workspace', work, '--handoff', bundle)
        (work / 'report.txt').write_text('Synthetic draft updated after the cutoff.\n', encoding='utf-8')
        current_bytes = file_bytes(work)
        after = cli('resume', '--workspace', work, '--handoff', bundle)
        old_states = {item['path']: item['status'] for item in before['comparisons']}
        new_states = {item['path']: item['status'] for item in after['comparisons']}
        if old_states != {'STATE.md': 'same', 'report.txt': 'same'}:
            raise AssertionError('original fixture identity did not match')
        if new_states != {'STATE.md': 'same', 'report.txt': 'changed'}:
            raise AssertionError('changed current artifact was not detected')
        if file_bytes(work) != current_bytes or cli('verify', bundle) != manifest:
            raise AssertionError('read-only inspection changed the workspace or bundle')
        result = {'installation_available': doctor['local_handoff_available'],
                  'task_id': manifest['task']['id'], 'bundle_integrity_verified': True,
                  'before': old_states, 'after': new_states,
                  'read_only_comparison_confirmed': True}
    if file_bytes(ROOT / 'examples') != original_examples:
        raise AssertionError('the repository example inputs were changed')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
