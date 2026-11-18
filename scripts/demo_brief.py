"""Offline synthetic example: inspect a small view, then a late correction."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/not_yet_dead.py'


def cli(workspace, *extra):
    call = subprocess.run(
        [sys.executable, '-B', str(SCRIPT), 'resume', '--workspace', str(workspace),
         '--brief', *extra], capture_output=True, text=True, encoding='utf-8', timeout=20)
    if call.returncode:
        raise RuntimeError(call.stderr)
    return json.loads(call.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix='nyd-brief-demo-') as directory:
        root = Path(directory).resolve()
        state = root / 'STATE.md'
        state.write_text('# Current\nDraft saved. Next: review report.txt.\n'
                         '## History\nEarlier synthetic draft.\n', encoding='utf-8', newline='\n')
        (root / 'DECISIONS.md').write_text(
            'Synthetic example: read-only review permitted; no publishing approval.\n',
            encoding='utf-8', newline='\n')
        before = state.read_bytes()
        small = cli(root)
        assert small['status'] == 'review_required'
        assert 'Earlier synthetic' not in small['documents'][0]['text']
        assert small['documents'][0]['sha256'] == hashlib.sha256(before).hexdigest()
        assert state.read_bytes() == before

        # This demonstration writes a fixture, not a production project.
        state.write_text(before.decode('utf-8') + '## Correction\n'
                         'Stop: the previous next step needs source review.\n', encoding='utf-8', newline='\n')
        corrected_bytes = state.read_bytes()
        detail = cli(root)
        assert detail['status'] == 'detail_required'
        assert all('text' not in doc for doc in detail['documents'])
        assert detail['documents'][0]['structural_conflicts'][0]['line'] == 5
        assert state.read_bytes() == corrected_bytes
        assert not (root / 'state.db').exists()
        assert not small['grants_execution'] and not detail['grants_execution']
        result = {
            'synthetic': True,
            'initial_status': small['status'],
            'history_omitted': small['documents'][0]['history_omitted'],
            'after_correction_status': detail['status'],
            'detail_reasons': detail['detail_reasons'],
            'correction_line': detail['documents'][0]['structural_conflicts'][0]['line'],
            'grants_execution': detail['grants_execution'],
            'read_only_inspection_confirmed': True,
        }
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
