"""Scoped file helpers: miswrite protection, not an OS/code sandbox.

The caller must authorize ``root``. There is deliberately no shell/command API.
"""
from pathlib import Path, PureWindowsPath
import os
import stat
import tempfile


def _reject_link(path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
        raise PermissionError('symlinks and reparse points are forbidden')


def safe_path(root, path):
    """Return a scoped path; reject traversal and ambiguous Windows names."""
    root = Path(root).absolute()
    _reject_link(root)
    root = root.resolve(strict=True)
    if not root.is_dir():
        raise ValueError('workspace root must be a directory')
    raw = str(path).replace('\\', '/')
    windows = PureWindowsPath(raw)
    if not raw or '\x00' in raw or raw.startswith('//') or (windows.drive and not windows.is_absolute()):
        raise ValueError('invalid or drive-relative path')
    if '..' in raw.split('/'):
        raise PermissionError('parent traversal is forbidden')
    candidate = Path(raw)
    if windows.drive and not candidate.is_absolute():
        raise PermissionError('foreign absolute path is forbidden')
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise PermissionError('path is outside workspace') from exc
    reserved = {'CON', 'PRN', 'AUX', 'NUL', *(f'COM{i}' for i in range(1, 10)), *(f'LPT{i}' for i in range(1, 10))}
    for part in relative.parts:
        if any(ord(c) < 32 or c in '<>:"|?*' for c in part) or part.endswith((' ', '.')) or part.split('.')[0].upper() in reserved:
            raise ValueError('ambiguous or reserved filename')
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        _reject_link(cursor)
    if not candidate.resolve().is_relative_to(root):
        raise PermissionError('resolved path is outside workspace')
    return candidate


def read_text(root, path, encoding='utf-8'):
    """Read a scoped regular text file without executing its contents."""
    target = safe_path(root, path)
    if not target.is_file():
        raise ValueError('not a regular file')
    return target.read_text(encoding=encoding)


def write_text(root, path, text, encoding='utf-8'):
    """Atomically replace a scoped file, never modify a hardlink's source."""
    target = safe_path(root, path)
    target.parent.mkdir(parents=True, exist_ok=True)
    safe_path(root, path)
    pending = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding=encoding, dir=target.parent,
                                         prefix='.ninnin-write-', delete=False) as stream:
            pending = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        safe_path(root, path)
        os.replace(pending, target)
    finally:
        if pending is not None and pending.exists():
            pending.unlink()
    return target


def list_files(root, path='.'):
    """Return sorted root-relative POSIX file names, refusing all links."""
    base = safe_path(root, path)
    if not base.is_dir():
        raise ValueError('list path must be a directory')
    root = Path(root).resolve(strict=True)
    result = []
    pending = [base]
    while pending:
        directory = pending.pop()
        for child in directory.iterdir():
            child = safe_path(root, child)
            if child.is_dir():
                pending.append(child)
            elif child.is_file():
                result.append(child.relative_to(root).as_posix())
            else:
                raise ValueError('not a regular file or directory')
    return sorted(result)
