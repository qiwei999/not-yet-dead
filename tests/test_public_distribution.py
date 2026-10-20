"""Public entrypoint and example coverage, using real local CLI subprocesses."""
from pathlib import Path
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/not_yet_dead.py'


def cli(*arguments):
    result = subprocess.run([sys.executable, '-B', str(SCRIPT), *map(str, arguments)],
                            capture_output=True, text=True, encoding='utf-8', timeout=20)
    if result.returncode:
        raise AssertionError(result.stderr)
    return json.loads(result.stdout)


class PublicDistributionTests(unittest.TestCase):
    def test_public_name_is_distinct_and_compatibility_entrypoint_remains_usable(self):
        self.assertIn('name: not-yet-dead', (ROOT / 'SKILL.md').read_text(encoding='utf-8'))
        public = cli('doctor')
        legacy = subprocess.run([sys.executable, '-B', str(ROOT / 'scripts/ninnin.py'), 'doctor'],
                                capture_output=True, text=True, encoding='utf-8', timeout=20)
        self.assertEqual(legacy.returncode, 0, legacy.stderr)
        self.assertEqual(public, json.loads(legacy.stdout))
        self.assertEqual(Path(public['core_path']).resolve(), (ROOT / 'lib/ninnin_core').resolve())
        self.assertEqual(set(public['commands']), {'doctor', 'resume', 'extract', 'verify', 'export', 'status'})

    def test_examples_make_a_verified_bundle_and_read_only_comparison(self):
        with tempfile.TemporaryDirectory(prefix='not-yet-dead-public-') as directory:
            base = Path(directory)
            work = base / 'current'
            shutil.copytree(ROOT / 'examples/workspace', work)
            bundle = base / 'handoff'
            cli('extract', '--snapshot', ROOT / 'examples/snapshot.json',
                '--checkpoint', ROOT / 'examples/checkpoint.json',
                '--workspace', work, '--out', bundle)
            manifest = cli('verify', bundle)
            self.assertEqual(manifest['task']['id'], 'demo-task')
            self.assertFalse(manifest['permissions']['execute'])
            initial = cli('resume', '--workspace', work, '--handoff', bundle)
            self.assertEqual({x['status'] for x in initial['comparisons']}, {'same'})
            report = work / 'report.txt'
            report.write_text('SYNTHETIC_NEW_DRAFT', encoding='utf-8')
            before = {p.relative_to(work).as_posix(): p.read_bytes()
                      for p in work.rglob('*') if p.is_file()}
            current = cli('resume', '--workspace', work, '--handoff', bundle)
            self.assertEqual({x['path']: x['status'] for x in current['comparisons']},
                             {'STATE.md': 'same', 'report.txt': 'changed'})
            self.assertEqual(before, {p.relative_to(work).as_posix(): p.read_bytes()
                                      for p in work.rglob('*') if p.is_file()})
            self.assertFalse(current['grants_execution'])
            self.assertEqual(cli('verify', bundle), manifest)

    def test_store_compatibility_commands_work_only_on_explicit_fixture_root(self):
        from ninnin_core.store import Store
        with tempfile.TemporaryDirectory(prefix='not-yet-dead-store-') as directory:
            root = Path(directory)
            store = Store(root)
            route = {'provider': 'fixture', 'model': 'offline'}
            room = store.create_room('Synthetic room', route, [route],
                                     authorization_id='synthetic-fixture-only', token_limit=1)
            task = store.create_task(room['id'], 'Synthetic task', 'Read saved records', route)
            self.assertEqual(cli('status', '--root', root)['rooms'], [room])
            bundle = root / 'exported-bundle'
            cli('export', '--root', root, '--task', task['id'], '--out', bundle)
            self.assertEqual(cli('verify', bundle)['task']['id'], task['id'])
            self.assertTrue((root / 'state.db').is_file())

    def test_markdown_relative_links_have_real_targets(self):
        for path in ROOT.rglob('*.md'):
            for target in re.findall(r'\]\(([^)]+)\)', path.read_text(encoding='utf-8')):
                if '://' in target or target.startswith(('#', 'mailto:')):
                    continue
                target = target.split('#', 1)[0]
                with self.subTest(source=path.relative_to(ROOT).as_posix(), target=target):
                    self.assertTrue((path.parent / target).exists(), 'broken public documentation link')


if __name__ == '__main__':
    unittest.main()
