"""Portable ninnin v1 handoffs built only from explicitly saved records.

No Hermes, Store, API client or execution runtime is imported. Hashes provide
integrity, not authenticity. A handoff never authorizes resuming a task.
"""
from pathlib import Path, PurePosixPath
from copy import deepcopy
import hashlib
import json
import os
import re
import shutil
import tempfile

from .workspace import safe_path, list_files


_SECTIONS = {
    'original_goal': '原始目标', 'latest_direction': '最新方向', 'route': '当前路线',
    'decisions': '公开关键决策依据', 'completed': '已完成', 'verified': '已验证',
    'changed': '改了什么', 'not_done': '未完成', 'risks': '风险', 'unknowns': '未知',
    'pending_confirmations': '待用户确认', 'environment': '产物与环境',
    'verification': '可复现验证方法', 'next_steps': '下一步',
}


def _json(value):
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False)


_PUBLIC_RESULT_KEYS = {'command', 'exit_code', 'stdout', 'stderr', 'text', 'timestamp',
                       'source', 'url', 'call_id', 'tool_call_id', 'tool', 'status', 'reason'}


def _public_results(records):
    return [{key: value for key, value in item.items() if key in _PUBLIC_RESULT_KEYS}
            for item in records]


def _public_events(events, task_id):
    result = []
    for event in events:
        kind = event.get('kind', '').lower()
        if any(word in kind for word in ('private', 'reasoning', 'thought')):
            continue
        if event.get('task_id') not in (None, task_id) or event.get('public') is False:
            continue
        payload = event.get('payload') or {}
        if payload.get('private') or payload.get('public') is False or payload.get('channel') == 'private':
            continue
        item = {key: event[key] for key in ('seq', 'timestamp', 'created_at', 'kind', 'task_id', 'run_id') if key in event}
        item['payload'] = _public_results([payload])[0]
        result.append(item)
    return result


_SECRET_TEXT = re.compile(r'''(?ix)
    (?:api[_-]?key|password|access[_-]?token|secret)["']?\s*[:=]\s*["']?[^\s,;}]+|
    \bsk-[A-Za-z0-9_-]{20,}|-----BEGIN\s+(?:RSA\s+|EC\s+|OPENSSH\s+)?PRIVATE\s+KEY-----|
    https?://[^\s/:@]+:[^\s/@]+@
''')
_SECRET_KEYS = {'api_key', 'apikey', 'password', 'secret', 'access_token', 'authorization', 'private_key', 'credentials'}


def _reject_secrets(value):
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower().replace('-', '_') in _SECRET_KEYS:
                raise PermissionError('credential fields cannot be exported')
            _reject_secrets(item)
    elif isinstance(value, list):
        for item in value:
            _reject_secrets(item)
    elif isinstance(value, str) and _SECRET_TEXT.search(value):
        raise PermissionError('secret-like content cannot be exported')


def _reject_sensitive_name(relative):
    blocked = {'.env', '.ssh', '.aws', 'soul.md', 'memory.md', 'user.md', 'identity.md',
               'auth.json', 'credentials.json', 'config.yaml', 'id_rsa', 'id_ed25519'}
    for part in PurePosixPath(relative).parts:
        if part.lower() in blocked or part.lower().startswith('.env.') or part.lower().endswith(('.pem', '.key')):
            raise PermissionError('credential or personal identity file cannot be exported')


def export_handoff(snapshot, checkpoint, output_dir, workspace=None):
    """Publish an all-or-nothing, non-overwriting verified export directory."""
    snapshot, checkpoint = deepcopy(snapshot), deepcopy(checkpoint)
    output = Path(output_dir).absolute()
    output.parent.mkdir(parents=True, exist_ok=True)
    output = safe_path(output.parent, output.name)
    if output.exists():
        raise FileExistsError('handoff output already exists')
    staging = Path(tempfile.mkdtemp(prefix='.ninnin-export-', dir=output.parent))
    try:
        pending = staging / 'bundle'
        _write_handoff(snapshot, checkpoint, pending, workspace)
        verify_handoff(pending)
        os.rename(pending, output)
    finally:
        shutil.rmtree(staging)
    return output


def _write_handoff(snapshot, checkpoint, output_dir, workspace):
    """Export saved task facts; unrecorded progress remains unknown."""
    task = snapshot.get('task', snapshot)
    run = snapshot.get('run') or {}
    checkpoint = checkpoint or {}
    saved = checkpoint.get('data', checkpoint)
    if checkpoint.get('task_id', task['id']) != task['id'] or run.get('task_id', task['id']) != task['id']:
        raise ValueError('checkpoint or run belongs to a different task')
    saved_generation = checkpoint.get('generation')
    task_generation = task.get('generation')
    saved_version = checkpoint.get('version', saved.get('direction_version'))
    if saved_generation is not None and task_generation is not None and saved_generation > task_generation:
        raise ValueError('checkpoint is from a future generation')
    checkpoint_seq = checkpoint.get('cutoff')
    if isinstance(checkpoint_seq, dict):
        checkpoint_seq = checkpoint_seq.get('event_seq')
    events = snapshot.get('events', [])
    sequence = snapshot.get('events_cursor', max((e['seq'] for e in events), default=checkpoint_seq))
    for value in (sequence, checkpoint_seq, *(event['seq'] for event in events)):
        if value is not None and (type(value) is not int or value < 0):
            raise ValueError('event cutoff must be a nonnegative integer or unknown')
    if checkpoint_seq is not None and sequence is not None and checkpoint_seq > sequence:
        raise ValueError('checkpoint lies beyond the task snapshot cutoff')
    events = [e for e in events if sequence is None or e['seq'] <= sequence]
    events = _public_events(events, task['id'])
    summary = {key: saved.get(key, task.get(key, '未记录，须复核。')) for key in _SECTIONS}
    summary['original_goal'] = task.get('original_goal', saved.get('original_goal', task.get('instructions', task.get('title', '未记录，须复核。'))))
    summary['latest_direction'] = saved.get('latest_direction', task.get('latest_direction', task.get('instructions', '未记录，须复核。')))
    if saved_generation is not None and task_generation is not None and saved_generation != task_generation:
        unknowns = summary['unknowns'] if isinstance(summary['unknowns'], list) else [summary['unknowns']]
        summary['unknowns'] = unknowns + [f'检查点世代 {saved_generation}，任务世代 {task_generation}；仅代表当时已保存记录，当前进展须复核。']
    if saved_version is not None and task.get('version') is not None and saved_version != task['version']:
        summary['latest_direction'] = task.get('latest_direction', task.get('instructions', '最新方向未记录，须确认。'))
        unknowns = summary['unknowns'] if isinstance(summary['unknowns'], list) else [summary['unknowns']]
        summary['unknowns'] = unknowns + [f"检查点方向版本 {saved_version}，任务方向版本 {task['version']}；旧阶段结果不等于已按新方向完成。"]
    output = Path(output_dir)
    output.mkdir(parents=True)
    (output / 'artifacts').mkdir()
    (output / 'evidence').mkdir()
    manifest = {
        'schema_version': 1,
        'task': {key: task[key] for key in ('id', 'title', 'version', 'generation') if key in task},
        'run': {key: run[key] for key in ('id', 'state', 'generation') if key in run},
        'direction_version': task.get('direction_version', task.get('version', saved.get('direction_version'))),
        'source_state': {'task': task.get('state', 'unknown'), 'run': run.get('state', 'unknown')},
        'cutoff': {'event_seq': sequence, 'checkpoint_seq': checkpoint_seq,
                   'checkpoint_generation': saved_generation,
                   'checkpoint_version': saved_version,
                   'checkpoint_at': checkpoint.get('created_at', checkpoint.get('timestamp'))},
        'summary': summary,
        'unconfirmed_side_effects': saved.get('unconfirmed_side_effects', ['未记录的外部副作用须先核对，不可盲目重做。']),
        'permissions': {'execute': False, 'resume_requires_confirmation': True},
    }
    _reject_secrets(manifest)
    text = '# ninnin 可携带交接\n\n'
    for key, heading in _SECTIONS.items():
        text += f'## {heading}\n{_json(summary[key])}\n\n'
    text += f"## 截止点\n{_json(manifest['cutoff'])}\n\n## 证据\nevidence/records.json\n\n"
    text += f"## 未确认副作用\n{_json(manifest['unconfirmed_side_effects'])}\n\n"
    text += '未保存的内部思考无法恢复。接手前需核验，继续须用户或总指挥确认。\n'
    (output / 'handoff.md').write_text(text, encoding='utf-8')
    records = dict(deepcopy(manifest), events=events, evidence=_public_results(saved.get('evidence', [])))
    records['attachment_snapshots'] = []
    _reject_secrets(records)
    (output / 'evidence' / 'records.json').write_text(_json(records), encoding='utf-8')
    for field, folder in (('artifacts', 'artifacts'), ('evidence_files', 'evidence')):
        references = [(item, False) for item in task.get(field, [])] + [(item, True) for item in saved.get(field, [])]
        for item, from_checkpoint in references:
            item = {'path': item} if isinstance(item, str) else item
            if workspace is None:
                raise ValueError('workspace is required for attachments')
            if not isinstance(item, dict) or not isinstance(item.get('path'), str):
                raise ValueError('attachment must contain a path')
            if item.get('approved') is False:
                raise PermissionError('attachment is not approved for export')
            source = safe_path(workspace, item['path'])
            relative = source.relative_to(Path(workspace).resolve()).as_posix()
            _reject_sensitive_name(relative)
            target = safe_path(output, f'{folder}/{relative}')
            if target.exists():
                raise ValueError('duplicate attachment or saved-record collision')
            if not source.is_file():
                raise ValueError('required attachment is not a regular file')
            before = source.stat()
            blob = source.read_bytes()
            after = source.stat()
            signature = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
            if signature(before) != signature(after) or len(blob) != after.st_size:
                raise ValueError('required attachment changed during export; take another checkpoint')
            _reject_secrets(blob.decode('utf-8', errors='ignore'))
            digest = hashlib.sha256(blob).hexdigest()
            if item.get('sha256') is not None and item['sha256'] != digest:
                raise ValueError('attachment checksum disagrees with saved evidence')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(blob)
            records['attachment_snapshots'].append({
                'path': target.relative_to(output).as_posix(), 'source': relative, 'sha256': digest,
                'cutoff_bound': from_checkpoint and item.get('sha256') is not None and checkpoint_seq is not None})
    text += '\n记录中的核验声明不是导出器重新执行的核验；接手需复核证据。\n'
    text += '\n## 必要附件：导出时快照\n只有检查点提供的 sha256 匹配时才标记截止点绑定；其余不得假定为历史截止点时内容。\n'
    text += _json(records['attachment_snapshots']) + '\n'
    (output / 'handoff.md').write_text(text, encoding='utf-8')
    (output / 'evidence' / 'records.json').write_text(_json(records), encoding='utf-8')
    manifest['files'] = []
    for item in sorted(output.rglob('*')):
        if item.is_file():
            blob = item.read_bytes()
            relative = item.relative_to(output).as_posix()
            manifest['files'].append({'path': relative, 'sha256': hashlib.sha256(blob).hexdigest(),
                                      'size': len(blob)})
    (output / 'manifest.json').write_text(_json(manifest), encoding='utf-8')
    return output


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _package_path(root, value):
    if not isinstance(value, str) or not value or '\\' in value or ':' in value:
        raise ValueError('package path must be canonical relative POSIX text')
    if any(part in ('', '.', '..') for part in value.split('/')) or PurePosixPath(value).is_absolute():
        raise ValueError('package traversal or absolute path is forbidden')
    return safe_path(root, value)


def verify_handoff(path):
    """Fail closed on unsupported/unsafe packages; never execute attachments."""
    path = Path(path)
    try:
        manifest = json.loads(safe_path(path, 'manifest.json').read_text(encoding='utf-8'), object_pairs_hook=_unique_object)
        required = {'schema_version', 'task', 'run', 'direction_version', 'source_state', 'cutoff', 'summary', 'unconfirmed_side_effects', 'permissions', 'files'}
        if not isinstance(manifest, dict) or set(manifest) != required:
            raise ValueError('incomplete handoff manifest')
        _reject_secrets(manifest)
        if type(manifest['schema_version']) is not int or manifest['schema_version'] != 1:
            raise ValueError('unsupported handoff version')
        if not isinstance(manifest['task'], dict) or not isinstance(manifest['task'].get('id'), str) or not manifest['task']['id']:
            raise ValueError('missing task identity')
        if not isinstance(manifest['summary'], dict) or set(manifest['summary']) != set(_SECTIONS):
            raise ValueError('incomplete task summary')
        if not isinstance(manifest['run'], dict) or not isinstance(manifest['cutoff'], dict) or not isinstance(manifest['source_state'], dict):
            raise ValueError('run, cutoff and source state must be objects')
        if set(manifest['task']) - {'id', 'title', 'version', 'generation'} or set(manifest['run']) - {'id', 'state', 'generation'}:
            raise ValueError('unsupported task or run fields')
        for key in ('version', 'generation'):
            if key in manifest['task'] and (type(manifest['task'][key]) is not int or manifest['task'][key] < 0):
                raise ValueError('invalid task version or generation')
        if 'generation' in manifest['run'] and (type(manifest['run']['generation']) is not int or manifest['run']['generation'] < 0):
            raise ValueError('invalid run generation')
        for record, keys in ((manifest['task'], ('title',)), (manifest['run'], ('id', 'state'))):
            if any(key in record and not isinstance(record[key], str) for key in keys):
                raise ValueError('invalid task/run text fields')
        if not isinstance(manifest['unconfirmed_side_effects'], list):
            raise ValueError('unconfirmed side effects must be an explicit list')
        cutoff = manifest['cutoff']
        if set(cutoff) != {'event_seq', 'checkpoint_seq', 'checkpoint_generation', 'checkpoint_version', 'checkpoint_at'}:
            raise ValueError('incomplete cutoff provenance')
        for value in (manifest['direction_version'], cutoff['event_seq'], cutoff['checkpoint_seq'], cutoff['checkpoint_generation'], cutoff['checkpoint_version']):
            if value is not None and (type(value) is not int or value < 0):
                raise ValueError('versions and cutoff sequences must be nonnegative integers or unknown')
        if cutoff['checkpoint_at'] is not None and not isinstance(cutoff['checkpoint_at'], str):
            raise ValueError('invalid checkpoint timestamp')
        if cutoff['event_seq'] is not None and cutoff['checkpoint_seq'] is not None and cutoff['checkpoint_seq'] > cutoff['event_seq']:
            raise ValueError('checkpoint exceeds event cutoff')
        if set(manifest['source_state']) != {'task', 'run'} or not all(isinstance(v, str) for v in manifest['source_state'].values()):
            raise ValueError('invalid source state')
        if manifest['permissions'] != {'execute': False, 'resume_requires_confirmation': True}:
            raise ValueError('handoff cannot grant execution or resume authority')
        if not isinstance(manifest['files'], list):
            raise ValueError('file index must be a list')
        indexed, saved_records = set(), None
        for entry in manifest['files']:
            if not isinstance(entry, dict) or set(entry) != {'path', 'size', 'sha256'}:
                raise ValueError('malformed file index entry')
            target = _package_path(path, entry['path'])
            name = entry['path']
            _reject_sensitive_name(name)
            if name != 'handoff.md' and not name.startswith(('artifacts/', 'evidence/')):
                raise ValueError('unexpected file index location')
            if name.casefold() in indexed:
                raise ValueError('duplicate file index location')
            indexed.add(name.casefold())
            if type(entry['size']) is not int or entry['size'] < 0 or not isinstance(entry['sha256'], str) or not re.fullmatch('[0-9a-f]{64}', entry['sha256']):
                raise ValueError('invalid file size or checksum')
            blob = target.read_bytes()
            _reject_secrets(blob.decode('utf-8', errors='ignore'))
            if len(blob) != entry['size'] or hashlib.sha256(blob).hexdigest() != entry['sha256']:
                raise ValueError('handoff file checksum or size mismatch')
            if name == 'evidence/records.json':
                saved_records = json.loads(blob.decode('utf-8'), object_pairs_hook=_unique_object)
        if not {'handoff.md', 'evidence/records.json'}.issubset(indexed):
            raise ValueError('handoff text and saved records must be indexed')
        if not isinstance(saved_records, dict) or any(saved_records.get(key) != value for key, value in manifest.items() if key != 'files'):
            raise ValueError('manifest facts disagree with checksummed saved records')
        actual = {name.casefold() for name in list_files(path)}
        if actual != indexed | {'manifest.json'}:
            raise ValueError('unindexed or missing package files')
        if not safe_path(path, 'artifacts').is_dir() or not safe_path(path, 'evidence').is_dir():
            raise ValueError('required package directories are missing')
        return manifest
    except (OSError, KeyError, TypeError) as exc:
        raise ValueError('inaccessible or malformed handoff package') from exc


def load_handoff(path):
    """Return verified manifest and human text as data, never executable code."""
    manifest = verify_handoff(path)
    blob = safe_path(path, 'handoff.md').read_bytes()
    entry = next(item for item in manifest['files'] if item['path'] == 'handoff.md')
    if len(blob) != entry['size'] or hashlib.sha256(blob).hexdigest() != entry['sha256']:
        raise ValueError('handoff text changed after verification')
    text = blob.decode('utf-8').replace('\r\n', '\n').replace('\r', '\n')
    return {'manifest': manifest, 'text': text}
