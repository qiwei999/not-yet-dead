"""Real alias-path regressions; all directories and content are synthetic."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from ninnin_core import workspace


def directory_alias(link, target):
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        if os.name != 'nt':
            raise
        result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(target)],
                                capture_output=True, timeout=10)
        if result.returncode:
            raise AssertionError(repr(result.stderr))


class PathAliasTests(unittest.TestCase):
    def test_real_read_accepts_absolute_paths_through_workspace_ancestor_alias(self):
        with tempfile.TemporaryDirectory(prefix='not-yet-dead-alias-') as directory:
            base = Path(directory).resolve()
            physical_parent = base / 'physical-parent'
            physical = physical_parent / 'workspace'
            physical.mkdir(parents=True)
            (physical / 'result.txt').write_text('SYNTHETIC_SAVED_RESULT', encoding='utf-8')
            alias_parent = base / 'alias-parent'
            directory_alias(alias_parent, physical_parent)
            alias = alias_parent / 'workspace'
            self.assertNotEqual(alias, physical)
            self.assertTrue(alias.samefile(physical))
            for root, target in ((alias, alias / 'result.txt'),
                                 (physical, alias / 'result.txt'),
                                 (alias, physical / 'result.txt')):
                with self.subTest(root=str(root), target=str(target)):
                    self.assertEqual(workspace.read_text(root, target), 'SYNTHETIC_SAVED_RESULT')
                    self.assertEqual(workspace.safe_path(root, target), physical / 'result.txt')


    def test_alias_support_keeps_inner_links_and_external_files_forbidden(self):
        with tempfile.TemporaryDirectory(prefix='not-yet-dead-alias-guard-') as directory:
            base = Path(directory).resolve()
            physical_parent = base / 'physical-parent'
            physical = physical_parent / 'workspace'
            physical.mkdir(parents=True)
            outside = base / 'outside'
            outside.mkdir()
            canary = outside / 'result.txt'
            canary.write_text('SYNTHETIC_PRIVATE_CANARY', encoding='utf-8')
            alias_parent = base / 'alias-parent'
            directory_alias(alias_parent, physical_parent)
            alias = alias_parent / 'workspace'
            directory_alias(physical / 'portal', outside)
            directory_alias(physical / 'loopback', physical)
            directory_alias(base / 'linked-root', physical)
            for root, target in ((physical, alias / 'portal/result.txt'),
                                 (alias, alias / 'portal/result.txt'),
                                 (physical, alias / 'loopback/result.txt'),
                                 (base / 'linked-root', 'result.txt'),
                                 (physical, base / 'linked-root/result.txt'),
                                 (alias, canary),
                                 (alias, alias / '../outside/result.txt')):
                with self.subTest(root=str(root), target=str(target)):
                    with self.assertRaises((PermissionError, ValueError)):
                        workspace.read_text(root, target)
            self.assertEqual(canary.read_text(encoding='utf-8'), 'SYNTHETIC_PRIVATE_CANARY')


if __name__ == '__main__':
    unittest.main()
