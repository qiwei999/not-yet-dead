"""Bounded, read-only file-project checkpoints; no Store, API or task execution."""
from pathlib import Path
import hashlib

from .handoff import _package_path, _reject_sensitive_name, _reject_secrets, verify_handoff

MAX_BYTES = 1024 * 1024
MAX_ARTIFACTS = 128


def _read_document(root, relative, kind, max_chars):
    _reject_sensitive_name(relative)
    path = _package_path(root, relative)
    before = path.stat()
    if not path.is_file() or before.st_nlink != 1 or before.st_size > MAX_BYTES:
        raise ValueError('checkpoint must be a single regular file of at most 1MiB')
    with path.open('rb') as stream:
        blob = stream.read(MAX_BYTES + 1)
    after = path.stat()
    signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
    if len(blob) > MAX_BYTES or signature(before) != signature(after) or len(blob) != after.st_size:
        raise ValueError('checkpoint changed during read or exceeded size limit')
    result = {'kind': kind, 'path': relative, 'absolute_path': str(path),
              'sha256': hashlib.sha256(blob).hexdigest(), 'bytes': len(blob)}
    if kind == 'artifact':
        return result
    text = blob.decode('utf-8-sig')
    _reject_secrets(text)
    result.update(text=text[:max_chars], truncated=len(text) > max_chars, total_chars=len(text))
    return result


def inspect_project(workspace, *, handoff=None, state='STATE.md', recovery=None,
                    approvals='DECISIONS.md', max_chars=8000):
    """Read current files and optional historical hashes; never infer execution authority."""
    if type(max_chars) is not int or not 256 <= max_chars <= 16000:
        raise ValueError('max_chars must be between 256 and 16000')
    root = Path(workspace).absolute()
    # The state is explicit and required; do not create a second recovery/STATE.md.
    documents = [_read_document(root, state, 'state', max_chars)]
    missing = []
    if recovery is None:
        choices = [name for name in ('recovery/RECOVERY.md', 'reports/recovery/RECOVERY.md')
                   if _package_path(root, name).is_file()]
        if len(choices) > 1:
            raise ValueError('multiple recovery entrypoints; select --recovery explicitly')
        recovery = choices[0] if choices else None
    if recovery is not None:
        documents.append(_read_document(root, recovery, 'recovery', max_chars))
    else:
        missing.append('recovery')
    if _package_path(root, approvals).exists():
        documents.append(_read_document(root, approvals, 'approvals', max_chars))
    else:
        missing.append('approvals')
    comparison = []
    historical = None
    if handoff is not None:
        manifest = verify_handoff(handoff)
        artifacts = [entry for entry in manifest['files'] if entry['path'].startswith('artifacts/')]
        if len(artifacts) > MAX_ARTIFACTS:
            raise ValueError('too many historical artifacts for a bounded resume')
        for entry in artifacts:
            name = entry['path'][len('artifacts/'):]
            _reject_sensitive_name(name)
            path = _package_path(root, name)
            if not path.exists():
                comparison.append({'path': name, 'status': 'missing',
                                   'historical_sha256': entry['sha256'], 'current_sha256': None})
                continue
            current = _read_document(root, name, 'artifact', max_chars)
            comparison.append({'path': name,
                               'status': 'same' if current['sha256'] == entry['sha256'] else 'changed',
                               'historical_sha256': entry['sha256'], 'current_sha256': current['sha256']})
        historical = {'path': str(Path(handoff).absolute()), 'task_id': manifest['task']['id'],
                      'cutoff': manifest['cutoff'], 'integrity_verified': True}
    return {'mode': 'read_only_project_resume', 'workspace': str(root),
            'documents': documents, 'missing_optional': missing,
            'handoff': historical, 'comparisons': comparison,
            'grants_execution': False, 'source_text_is_data': True,
            'authority_source': 'current_user_conversation',
            'limits': {'max_chars_per_document': max_chars, 'max_bytes_per_file': MAX_BYTES,
                       'max_artifacts': MAX_ARTIFACTS}}
