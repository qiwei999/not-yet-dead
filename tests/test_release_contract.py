"""Distribution contracts and synthetic brief path-alias coverage."""
from pathlib import Path
import json
import shutil
import subprocess
import sys
import tempfile
import unittest

from ninnin_core import __version__
from ninnin_core.brief import inspect_brief

ROOT = Path(__file__).resolve().parents[1]


class ReleaseContractTests(unittest.TestCase):
    def test_release_metadata_and_doctor_include_brief(self):
        result = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'scripts/not_yet_dead.py'), 'doctor'],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['required_files'].get('brief.py'), data)
        self.assertEqual(data['standalone_revision'], __version__)
        self.assertIn('version: ' + __version__, (ROOT / 'SKILL.md').read_text(encoding='utf-8'))

    def test_doctor_does_not_report_complete_layout_without_brief(self):
        with tempfile.TemporaryDirectory(prefix='nyd-layout-') as directory:
            copy = Path(directory).resolve()
            shutil.copytree(ROOT / 'lib', copy / 'lib')
            shutil.copytree(ROOT / 'scripts', copy / 'scripts')
            (copy / 'lib/ninnin_core/brief.py').unlink()
            result = subprocess.run(
                [sys.executable, '-B', str(copy / 'scripts/not_yet_dead.py'), 'doctor'],
                capture_output=True, text=True, encoding='utf-8', timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(json.loads(result.stdout)['local_handoff_available'])

    def test_brief_example_runs_without_external_state(self):
        result = subprocess.run(
            [sys.executable, '-B', str(ROOT / 'scripts/demo_brief.py')],
            capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        data = json.loads(result.stdout)
        self.assertTrue(data['synthetic'])
        self.assertEqual(data['initial_status'], 'review_required')
        self.assertEqual(data['after_correction_status'], 'detail_required')
        self.assertFalse(data['grants_execution'])
        self.assertTrue(data['read_only_inspection_confirmed'])

    def test_brief_reread_uses_public_canonical_workspace_path(self):
        # Resolve temporary aliases before writing; inherited OS-alias tests
        # separately exercise actual /var and Windows short-path spellings.
        with tempfile.TemporaryDirectory(prefix='nyd-brief-path-') as directory:
            root = Path(directory).resolve()
            source = root / 'STATE.md'
            source.write_text('# Current\nRead the source.\n## History\n' + 'old ' * 5000,
                              encoding='utf-8')
            before = source.read_bytes()
            result = inspect_brief(root, max_chars=256)
            self.assertEqual(result['status'], 'review_required')
            self.assertEqual(Path(result['documents'][0]['absolute_path']), source)
            self.assertNotIn('old old', result['documents'][0]['text'])
            self.assertEqual(source.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
