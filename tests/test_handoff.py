"""Portable saved-record handoffs; no network or live profiles."""
import hashlib
import importlib
import json
from pathlib import Path
import shutil
import tempfile
import unittest

SCRATCH = Path(tempfile.gettempdir()).resolve()


class HandoffTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ninnin-handoff-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.work = self.root / '工作区'
        self.work.mkdir()
        self.task = {'id': 'task-a', 'title': '离线报告', 'instructions': '形成可核验报告',
                     'state': 'stopped', 'version': 2, 'generation': 3}

    def module(self):
        try:
            return importlib.import_module('ninnin_core.handoff')
        except ModuleNotFoundError as exc:
            self.fail(f'handoff module is not implemented: {exc}')

    def test_plain_task_exports_human_readable_saved_state_not_invented_thinking(self):
        output = self.module().export_handoff(self.task, None, self.root / '包')
        self.assertEqual(output, self.root / '包')
        self.assertTrue((output / 'artifacts').is_dir())
        self.assertTrue((output / 'evidence').is_dir())
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['schema_version'], 1)
        self.assertEqual(manifest['task']['id'], 'task-a')
        self.assertEqual(manifest['task']['generation'], 3)
        self.assertEqual(manifest['source_state']['task'], 'stopped')
        text = (output / 'handoff.md').read_text(encoding='utf-8')
        self.assertIn('形成可核验报告', text)
        for heading in ['最新方向', '已完成', '未完成', '未知', '证据', '截止点', '下一步']:
            self.assertIn(heading, text)
        self.assertIn('未保存的内部思考无法恢复', text)
        self.assertFalse(manifest['permissions']['execute'])
        self.assertTrue(manifest['permissions']['resume_requires_confirmation'])
    def test_enveloped_snapshot_binds_public_checkpoint_to_event_cutoff(self):
        module = self.module()
        checkpoint = {'task_id': 'task-a', 'generation': 3, 'cutoff': 7,
                      'created_at': '2026-10-17T02:00:00+00:00', 'data': {
                          'latest_direction': '先核验，不执行远端提交', 'completed': ['生成草稿'],
                          'verified': ['本地命令 exit=0'], 'changed': ['report.txt'],
                          'not_done': ['尚未复核'], 'unknowns': ['远端副作用未确认'],
                          'decisions': ['只采用公开结果'], 'risks': ['外部依赖'],
                          'pending_confirmations': ['确认继续'], 'environment': {'python': 'stdlib'},
                          'verification': ['python -m unittest'], 'next_steps': ['读取证据']}}
        snapshot = {'task': self.task, 'run': {'id': 'run-a', 'state': 'interrupted', 'generation': 3},
                    'events_cursor': 7, 'events': [
                        {'seq': 6, 'kind': 'tool_started', 'task_id': 'task-a', 'payload': {'command': 'check'}},
                        {'seq': 7, 'kind': 'checkpoint', 'task_id': 'task-a', 'payload': {'text': 'checkpoint saved'}},
                        {'seq': 8, 'kind': 'progress', 'task_id': 'task-a', 'payload': {'text': 'FUTURE_NOT_AT_CUTOFF'}}]}
        output = module.export_handoff(snapshot, checkpoint, self.root / '包')
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['task'].get('id'), 'task-a', 'enveloped task was not extracted')
        self.assertEqual(manifest['run']['id'], 'run-a')
        self.assertEqual(manifest['cutoff']['event_seq'], 7)
        self.assertEqual(manifest['cutoff']['checkpoint_seq'], 7)
        self.assertEqual(manifest['direction_version'], 2)
        self.assertEqual(manifest['summary']['completed'], ['生成草稿'])
        self.assertEqual(manifest['summary']['not_done'], ['尚未复核'])
        text = (output / 'handoff.md').read_text(encoding='utf-8')
        for fact in ['先核验，不执行远端提交', '本地命令 exit=0', '尚未复核', '远端副作用未确认', '确认继续']:
            self.assertIn(fact, text)
        records = json.loads((output / 'evidence' / 'records.json').read_text(encoding='utf-8'))
        self.assertEqual([event['seq'] for event in records['events']], [6, 7])
        self.assertNotIn('FUTURE_NOT_AT_CUTOFF', json.dumps(manifest) + json.dumps(records))
    def test_export_copies_required_artifacts_and_evidence_with_byte_checksums(self):
        module = self.module()
        (self.work / 'results').mkdir()
        artifact = self.work / 'results' / '报告.txt'
        artifact.write_bytes('真实产物\n'.encode('utf-8'))
        (self.work / 'checks').mkdir()
        evidence = self.work / 'checks' / 'output.log'
        evidence.write_bytes(b'command=unittest\nexit=0\n')
        expected_hash = hashlib.sha256(artifact.read_bytes()).hexdigest()
        checkpoint = {'artifacts': [{'path': 'results/报告.txt', 'sha256': expected_hash}],
                      'evidence_files': ['checks/output.log'], 'completed': ['写入报告']}
        output = module.export_handoff(self.task, checkpoint, self.root / 'export', self.work)
        self.assertTrue((output / 'artifacts/results/报告.txt').is_file(), 'artifact bytes were not copied')
        self.assertEqual((output / 'artifacts/results/报告.txt').read_bytes(), artifact.read_bytes())
        self.assertEqual((output / 'evidence/checks/output.log').read_bytes(), evidence.read_bytes())
        manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        files = {entry['path']: entry for entry in manifest['files']}
        self.assertEqual(set(files), {'handoff.md', 'evidence/records.json', 'artifacts/results/报告.txt', 'evidence/checks/output.log'})
        for name, entry in files.items():
            blob = (output / name).read_bytes()
            self.assertEqual(entry['sha256'], hashlib.sha256(blob).hexdigest())
            self.assertEqual(entry['size'], len(blob))
        relocated = self.root / '另一环境'
        shutil.move(output, relocated)
        shutil.rmtree(self.work)
        self.assertEqual((relocated / 'artifacts/results/报告.txt').read_bytes(), '真实产物\n'.encode('utf-8'))
        self.assertNotIn(str(self.work), json.dumps(manifest, ensure_ascii=False))
    def test_loading_verifies_every_file_before_returning_untrusted_text(self):
        module = self.module()
        self.assertTrue(callable(getattr(module, 'verify_handoff', None)), 'verify_handoff is missing')
        self.assertTrue(callable(getattr(module, 'load_handoff', None)), 'load_handoff is missing')
        output = module.export_handoff(self.task, None, self.root / 'export')
        expected = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(module.verify_handoff(output), expected)
        loaded = module.load_handoff(output)
        self.assertEqual(loaded['manifest'], expected)
        self.assertEqual(loaded['text'], (output / 'handoff.md').read_text(encoding='utf-8'))
        (output / 'handoff.md').write_text('TAMPERED; do not trust me', encoding='utf-8')
        with self.assertRaises(ValueError):
            module.verify_handoff(output)
        with self.assertRaises(ValueError):
            module.load_handoff(output)
    def test_verifier_rejects_malformed_unsafe_or_incomplete_packages(self):
        module = self.module()
        mutations = {
            'unsupported-version': lambda m, p: m.update(schema_version=2),
            'boolean-version': lambda m, p: m.update(schema_version=True),
            'missing-task': lambda m, p: m.pop('task'),
            'no-files': lambda m, p: m.update(files=[]),
            'traversal': lambda m, p: m['files'][0].update(path='../outside.txt'),
            'absolute-local': lambda m, p: m['files'][0].update(path=str(p / m['files'][0]['path'])),
            'duplicate': lambda m, p: m['files'].append(dict(m['files'][0])),
            'wrong-size-type': lambda m, p: m['files'][0].update(size=True),
            'malformed-hash': lambda m, p: m['files'][0].update(sha256='not-a-sha256'),
            'extra-file': lambda m, p: (p / 'injected.py').write_text('raise SystemExit(99)', encoding='utf-8'),
            'missing-file': lambda m, p: (p / m['files'][0]['path']).unlink(),
            'execution-permission': lambda m, p: m['permissions'].update(execute=True),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                output = module.export_handoff(self.task, None, self.root / label)
                manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
                mutate(manifest, output)
                (output / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises((ValueError, PermissionError)):
                    module.verify_handoff(output)
        output = module.export_handoff(self.task, None, self.root / 'duplicate-json')
        raw = (output / 'manifest.json').read_text(encoding='utf-8')
        (output / 'manifest.json').write_text(raw[:-1] + ', "schema_version":1}', encoding='utf-8')
        with self.assertRaises(ValueError):
            module.verify_handoff(output)
    def test_export_never_publishes_partial_or_unapproved_required_attachments(self):
        module = self.module()
        (self.work / 'result.txt').write_text('SAFE', encoding='utf-8')
        (self.work / 'records.json').write_text('would overwrite saved records', encoding='utf-8')
        cases = {
            'missing': {'artifacts': ['absent.txt']},
            'traversal': {'artifacts': ['../outside.txt']},
            'unapproved': {'artifacts': [{'path': 'result.txt', 'approved': False}]},
            'checksum': {'artifacts': [{'path': 'result.txt', 'sha256': '0' * 64}]},
            'duplicate': {'artifacts': ['result.txt', 'result.txt']},
            'records-collision': {'evidence_files': ['records.json']},
        }
        for label, checkpoint in cases.items():
            with self.subTest(case=label):
                output = self.root / label
                with self.assertRaises((ValueError, PermissionError, OSError)):
                    module.export_handoff(self.task, checkpoint, output, self.work)
                self.assertFalse(output.exists(), 'a failed export published a partial package')
        output = self.root / 'no-workspace'
        with self.assertRaises(ValueError):
            module.export_handoff(self.task, {'artifacts': ['result.txt']}, output)
        self.assertFalse(output.exists())
        existing = self.root / 'existing'
        existing.mkdir()
        (existing / 'canary').write_text('UNCHANGED', encoding='utf-8')
        with self.assertRaises((ValueError, FileExistsError)):
            module.export_handoff(self.task, None, existing)
        self.assertEqual((existing / 'canary').read_text(encoding='utf-8'), 'UNCHANGED')
        self.assertFalse(list(self.root.glob('.ninnin-export-*')))
    def test_only_saved_public_evidence_is_exported_and_private_content_is_not(self):
        module = self.module()
        task = dict(self.task, private_thoughts='NEVER_INTERNAL', api_key='NEVER_CREDENTIAL',
                    route={'provider': 'local-test', 'model': 'm', 'key_env': 'TEST_KEY_REFERENCE'})
        checkpoint = {'data': {'completed': ['saved public result'], 'private_thoughts': 'NEVER_CP',
                              'evidence': [{'command': 'check', 'exit_code': 0, 'stdout': 'REAL_SAVED_RESULT'}],
                              'unconfirmed_side_effects': ['remote operation not confirmed']}}
        snapshot = {'task': task, 'events': [
            {'seq': 1, 'kind': 'private_message', 'payload': {'text': 'NEVER_PRIVATE'}},
            {'seq': 2, 'kind': 'reasoning', 'payload': {'text': 'NEVER_REASONING'}},
            {'seq': 3, 'kind': 'progress', 'task_id': 'another-task', 'payload': {'text': 'NEVER_OTHER_TASK'}},
            {'seq': 4, 'kind': 'tool_completed', 'task_id': 'task-a',
             'payload': {'stdout': 'PUBLIC_TOOL_RESULT', 'internal_thoughts': 'NEVER_PAYLOAD'}}]}
        output = module.export_handoff(snapshot, checkpoint, self.root / 'public')
        manifest = module.verify_handoff(output)
        records = json.loads((output / 'evidence/records.json').read_text(encoding='utf-8'))
        all_text = '\n'.join(path.read_text(encoding='utf-8') for path in output.rglob('*') if path.is_file())
        self.assertNotIn('NEVER_', all_text, 'private or unrelated saved content leaked')
        self.assertIn('REAL_SAVED_RESULT', all_text)
        self.assertIn('PUBLIC_TOOL_RESULT', all_text)
        self.assertEqual([e['seq'] for e in records['events']], [4])
        self.assertEqual(manifest['unconfirmed_side_effects'], ['remote operation not confirmed'])
        self.assertIn('remote operation not confirmed', (output / 'handoff.md').read_text(encoding='utf-8'))
        self.assertEqual(manifest['summary']['route']['key_env'], 'TEST_KEY_REFERENCE')
    def test_export_blocks_credentials_identity_files_and_secret_like_public_text(self):
        module = self.module()
        for name, content in [('.env', 'TEST_ONLY=1'), ('SOUL.md', 'identity canary'),
                              ('MEMORY.md', 'personal canary'), ('auth.json', '{}'),
                              ('public.txt', 'api_key=FAKE_TEST_ONLY_CREDENTIAL')]:
            (self.work / name).write_text(content, encoding='utf-8')
            output = self.root / ('blocked-' + name.replace('.', '-'))
            with self.subTest(file=name):
                with self.assertRaises(PermissionError):
                    module.export_handoff(self.task, {'artifacts': [name]}, output, self.work)
                self.assertFalse(output.exists())
                self.assertEqual((self.work / name).read_text(encoding='utf-8'), content)
        with self.assertRaises(PermissionError):
            module.export_handoff(self.task, {'latest_direction': 'password=FAKE_TEST_ONLY'}, self.root / 'secret-text')
        task = dict(self.task, route={'provider': 'test', 'model': 'm', 'api_key': 'FAKE_TEST_ONLY'})
        with self.assertRaises(PermissionError):
            module.export_handoff(task, None, self.root / 'secret-route')
    def test_checkpoint_scope_and_generations_are_honest_at_the_saved_cutoff(self):
        module = self.module()
        snapshot = {'task': self.task, 'run': {'id': 'run-old', 'task_id': 'task-a', 'generation': 2, 'state': 'stopped'},
                    'events_cursor': 9, 'events': [{'seq': 9, 'kind': 'run_stopped', 'payload': {}}]}
        old = {'task_id': 'task-a', 'generation': 2, 'cutoff': {'event_seq': 8}, 'data': {'completed': ['saved before stop']}}
        output = module.export_handoff(snapshot, old, self.root / 'old-saved')
        manifest = module.verify_handoff(output)
        self.assertEqual(manifest['cutoff'].get('checkpoint_generation'), 2, 'saved-generation provenance is missing')
        self.assertEqual(manifest['cutoff']['checkpoint_seq'], 8)
        self.assertIn('检查点世代', json.dumps(manifest['summary']['unknowns'], ensure_ascii=False))
        self.assertEqual(manifest['summary']['completed'], ['saved before stop'])
        for label, snap, checkpoint in [
            ('foreign-checkpoint', snapshot, {'task_id': 'another-task'}),
            ('future-generation', snapshot, {'generation': 4}),
            ('future-checkpoint', snapshot, {'cutoff': 10}),
            ('bad-sequence', dict(snapshot, events_cursor=-1), None),
            ('foreign-run', {'task': self.task, 'run': {'task_id': 'another-task'}}, None),
        ]:
            with self.subTest(case=label):
                with self.assertRaises(ValueError):
                    module.export_handoff(snap, checkpoint, self.root / label)
                self.assertFalse((self.root / label).exists())
    def test_export_aborts_when_required_artifact_changes_during_copy(self):
        from unittest.mock import patch
        module = self.module()
        artifact = self.work / 'changing.txt'
        artifact.write_bytes(b'BEFORE')
        original_read = Path.read_bytes
        def changing_read(path):
            blob = original_read(path)
            if path == artifact:
                artifact.write_bytes(b'AFTER_DIFFERENT_BYTES')
            return blob
        output = self.root / 'racing'
        with patch.object(Path, 'read_bytes', changing_read):
            with self.assertRaises(ValueError):
                module.export_handoff(self.task, {'artifacts': ['changing.txt']}, output, self.work)
        self.assertFalse(output.exists(), 'concurrently changing bytes must not be published as a stable snapshot')
        self.assertEqual(artifact.read_bytes(), b'AFTER_DIFFERENT_BYTES')
    def test_manifest_matches_documented_v1_shape_and_rejects_wrong_fact_types(self):
        module = self.module()
        schema_path = Path(__file__).resolve().parents[1] / 'schemas/handoff-v1.schema.json'
        self.assertTrue(schema_path.is_file(), 'portable v1 JSON schema is missing')
        schema = json.loads(schema_path.read_text(encoding='utf-8'))
        self.assertEqual(schema['properties']['schema_version']['const'], 1)
        output = module.export_handoff(self.task, None, self.root / 'schema-valid')
        manifest = module.verify_handoff(output)
        self.assertEqual(set(schema['required']), set(manifest))
        for label, field, value in [('summary-type', 'summary', None), ('cutoff-type', 'cutoff', []),
                                    ('run-type', 'run', 'not-a-run'), ('source-type', 'source_state', None),
                                    ('direction-type', 'direction_version', True),
                                    ('side-effects-type', 'unconfirmed_side_effects', {})]:
            with self.subTest(case=label):
                modified = dict(manifest, **{field: value})
                (output / 'manifest.json').write_text(json.dumps(modified), encoding='utf-8')
                with self.assertRaises(ValueError):
                    module.verify_handoff(output)
    def test_input_mutation_cannot_change_the_captured_snapshot_mid_export(self):
        from unittest.mock import patch
        module = self.module()
        artifact = self.work / 'result.txt'
        artifact.write_text('SAVED_BYTES', encoding='utf-8')
        checkpoint = {'completed': ['CAPTURED'], 'artifacts': ['result.txt']}
        original_read = Path.read_bytes
        def mutate_caller_after_capture(path):
            if path == artifact:
                checkpoint['completed'].append('LATER_CALLER_CHANGE')
                self.task['instructions'] = 'NEW_DIRECTION_NOT_CAPTURED'
            return original_read(path)
        with patch.object(Path, 'read_bytes', mutate_caller_after_capture):
            output = module.export_handoff(self.task, checkpoint, self.root / 'captured', self.work)
        manifest = module.verify_handoff(output)
        self.assertEqual(manifest['summary']['completed'], ['CAPTURED'], 'caller mutation changed exported facts')
        self.assertEqual(manifest['summary']['original_goal'], '形成可核验报告')
        self.assertIn('LATER_CALLER_CHANGE', checkpoint['completed'])
        self.assertNotIn('LATER_CALLER_CHANGE', (output / 'evidence/records.json').read_text(encoding='utf-8'))
    def test_manifest_facts_cannot_disagree_with_checksummed_saved_records(self):
        module = self.module()
        mutations = {
            'invented-progress': lambda m: m['summary'].update(completed=['NOT_IN_SAVED_RECORDS']),
            'changed-cutoff': lambda m: m['cutoff'].update(event_seq=99),
            'invalid-generation': lambda m: m['task'].update(generation=True),
            'negative-version': lambda m: m['task'].update(version=-1),
            'unknown-task-field': lambda m: m['task'].update(private_thoughts='UNSUPPORTED'),
            'invalid-run': lambda m: m['run'].update(generation=-2),
            'unknown-file-field': lambda m: m['files'][0].update(execute='NEVER_EXECUTE'),
        }
        for label, mutate in mutations.items():
            with self.subTest(case=label):
                output = module.export_handoff(self.task, None, self.root / label)
                manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
                mutate(manifest)
                (output / 'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
                with self.assertRaises(ValueError):
                    module.verify_handoff(output)
    def test_loader_never_returns_text_changed_after_the_integrity_pass(self):
        from unittest.mock import patch
        module = self.module()
        output = module.export_handoff(self.task, None, self.root / 'load-race')
        handoff = output / 'handoff.md'
        expected = handoff.read_text(encoding='utf-8')
        real_read = Path.read_bytes
        mutated = False
        def mutate_after_read(path):
            nonlocal mutated
            blob = real_read(path)
            if path == handoff and not mutated:
                mutated = True
                handoff.write_text('UNVERIFIED_LATE_REPLACEMENT', encoding='utf-8')
            return blob
        with patch.object(Path, 'read_bytes', mutate_after_read):
            try:
                loaded = module.load_handoff(output)
            except ValueError:
                pass
            else:
                self.assertEqual(loaded['text'], expected, 'loader returned text whose bytes it never verified')
        self.assertTrue(mutated)
    def test_store_checkpoint_timestamp_and_old_direction_version_remain_explicit(self):
        module = self.module()
        task = dict(self.task, original_goal='原始目标未改', instructions='用户已改为只读核验')
        checkpoint = {'task_id': 'task-a', 'generation': 2, 'version': 1, 'cutoff': 4,
                      'timestamp': '2026-10-17T02:00:00+00:00', 'data': {
                          'latest_direction': '旧方向：进行写入', 'direction_version': 1, 'completed': ['旧阶段产物']}}
        output = module.export_handoff({'task': task, 'events_cursor': 5, 'events': []}, checkpoint, self.root / 'store-shape')
        manifest = module.verify_handoff(output)
        self.assertEqual(manifest['cutoff']['checkpoint_at'], checkpoint['timestamp'], 'Store timestamp was lost')
        self.assertEqual(manifest['cutoff'].get('checkpoint_version'), 1)
        self.assertEqual(manifest['direction_version'], 2)
        self.assertEqual(manifest['summary']['latest_direction'], '用户已改为只读核验')
        self.assertEqual(manifest['summary']['original_goal'], '原始目标未改')
        self.assertEqual(manifest['summary']['completed'], ['旧阶段产物'])
        self.assertIn('方向版本', json.dumps(manifest['summary']['unknowns'], ensure_ascii=False))
    def test_attachment_provenance_distinguishes_export_time_copies_from_saved_hashes(self):
        module = self.module()
        (self.work / 'raw.txt').write_bytes(b'EXPORT_TIME_BYTES')
        (self.work / 'bound.txt').write_bytes(b'CHECKPOINT_BYTES')
        digest = hashlib.sha256(b'CHECKPOINT_BYTES').hexdigest()
        checkpoint = {'cutoff': 7, 'data': {'verified': ['saved assertion, not rerun'],
                      'artifacts': ['raw.txt', {'path': 'bound.txt', 'sha256': digest}]}}
        output = module.export_handoff(self.task, checkpoint, self.root / 'provenance', self.work)
        records = json.loads((output / 'evidence/records.json').read_text(encoding='utf-8'))
        self.assertIn('attachment_snapshots', records, 'attachment time/provenance evidence missing')
        entries = {entry['path']: entry for entry in records['attachment_snapshots']}
        self.assertFalse(entries['artifacts/raw.txt']['cutoff_bound'])
        self.assertTrue(entries['artifacts/bound.txt']['cutoff_bound'])
        self.assertEqual(entries['artifacts/bound.txt']['sha256'], digest)
        text = module.load_handoff(output)['text']
        self.assertIn('artifacts/raw.txt', text)
        self.assertIn('导出时快照', text)
        self.assertIn('记录中的核验声明', text)


if __name__ == '__main__':
    unittest.main()
