"""Scoped-file behavior; fixtures never touch a real Hermes profile."""
import importlib
from pathlib import Path
import tempfile
import unittest

SCRATCH = Path(tempfile.gettempdir()).resolve()


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ninnin-workspace-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / '工作区'
        self.root.mkdir()

    def module(self):
        try:
            return importlib.import_module('ninnin_core.workspace')
        except ModuleNotFoundError as exc:
            self.fail(f'workspace module is not implemented: {exc}')

    def test_safe_path_accepts_unicode_relative_file(self):
        result = self.module().safe_path(self.root, '产物/说明.txt')
        self.assertEqual(result, self.root / '产物' / '说明.txt')
    def test_safe_path_rejects_unscoped_or_ambiguous_paths(self):
        module = self.module()
        outside = self.root.parent / 'sibling' / 'secret.txt'
        dangerous = ['../secret', 'dir/../../secret', r'..\secret', str(outside),
                     r'C:relative.txt', r'\\server\share\secret', r'\\?\C:\secret',
                     'data.txt:stream', 'name. ', 'NUL.txt', 'aux', 'dir/../note', '\x00bad']
        for value in dangerous:
            with self.subTest(path=value):
                with self.assertRaises((ValueError, PermissionError)):
                    module.safe_path(self.root, value)
        self.assertEqual(module.safe_path(self.root, self.root / 'scoped.txt'), self.root / 'scoped.txt')
    def test_safe_path_refuses_symlink_or_junction_components(self):
        import os
        import subprocess
        module = self.module()
        outside = self.root.parent / 'private'
        outside.mkdir()
        (outside / 'secret.txt').write_text('CANARY', encoding='utf-8')
        link = self.root / 'portal'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, repr(result.stderr))
        for root, relative in [(self.root, 'portal/secret.txt'), (link, 'secret.txt')]:
            with self.subTest(root=str(root)):
                with self.assertRaises(PermissionError):
                    module.safe_path(root, relative)
        self.assertEqual((outside / 'secret.txt').read_text(encoding='utf-8'), 'CANARY')
    def test_scoped_text_roundtrip_does_not_modify_linked_original(self):
        import os
        module = self.module()
        self.assertTrue(callable(getattr(module, 'write_text', None)), 'scoped write_text is missing')
        outside = self.root.parent / 'original.txt'
        outside.write_text('ORIGINAL', encoding='utf-8')
        os.link(outside, self.root / 'shared.txt')
        result = module.write_text(self.root, 'shared.txt', '独立副本')
        self.assertEqual(result, self.root / 'shared.txt')
        self.assertEqual(module.read_text(self.root, 'shared.txt'), '独立副本')
        self.assertEqual(outside.read_text(encoding='utf-8'), 'ORIGINAL')
        module.write_text(self.root, '新目录/说明.md', '中文\nline')
        self.assertEqual(module.read_text(self.root, '新目录/说明.md'), '中文\nline')
        with self.assertRaises(PermissionError):
            module.write_text(self.root, '../original.txt', 'BAD')
        with self.assertRaises(PermissionError):
            module.read_text(self.root, '../original.txt')
    def test_list_files_is_deterministic_scoped_and_never_follows_links(self):
        module = self.module()
        self.assertTrue(callable(getattr(module, 'list_files', None)), 'scoped list_files is missing')
        (self.root / 'z.txt').write_text('z', encoding='utf-8')
        (self.root / '产物').mkdir()
        (self.root / '产物' / 'a.txt').write_text('a', encoding='utf-8')
        self.assertEqual(module.list_files(self.root), ['z.txt', '产物/a.txt'])
        self.assertEqual(module.list_files(self.root, '产物'), ['产物/a.txt'])
        with self.assertRaises(PermissionError):
            module.list_files(self.root, '..')
        import os
        import subprocess
        outside = self.root.parent / 'sibling'
        outside.mkdir()
        link = self.root / 'leak'
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            if os.name != 'nt':
                raise
            result = subprocess.run(['cmd.exe', '/d', '/c', 'mklink', '/J', str(link), str(outside)], capture_output=True)
            self.assertEqual(result.returncode, 0, repr(result.stderr))
        with self.assertRaises(PermissionError):
            module.list_files(self.root)


if __name__ == '__main__':
    unittest.main()
