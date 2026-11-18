"""Synthetic layout counterexamples; real standalone CLI, no network/model calls."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path

SKILL=Path(__file__).resolve().parents[1]

class StructuralConflictTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(prefix='ninnin-conflict-')
  self.addCleanup(self.tmp.cleanup)
  self.work=Path(self.tmp.name).resolve()/'当前项目';self.work.mkdir()
 def call(self,text,*extra):
  p=self.work/'STATE.md';p.write_text(text,encoding='utf-8');before=p.read_bytes()
  q=subprocess.run([sys.executable,'-B',str(SKILL/'scripts/not_yet_dead.py'),'resume','--workspace',str(self.work),'--brief',*extra],capture_output=True,text=True,encoding='utf-8',timeout=20)
  self.assertEqual(q.returncode,0,q.stderr);self.assertEqual(p.read_bytes(),before)
  return json.loads(q.stdout),hashlib.sha256(before).hexdigest()
 def test_late_correction_requires_source_instead_of_stale_prefix(self):
  data,digest=self.call('# 当前\n下一步继续处理请求。\n## 历史\n旧记录。\n## 最新更正\n停止；unknown请求不得重发。')
  self.assertEqual(data['status'],'detail_required')
  self.assertIn('history_followed_by_current_heading',data['detail_reasons'])
  self.assertTrue(all('text' not in d and d['excerpt_unavailable'] for d in data['documents']))
  self.assertEqual(data['documents'][0]['structural_conflicts'],[{'code':'history_followed_by_current_heading','line':5}])
  self.assertEqual(data['documents'][0]['path'],'STATE.md');self.assertEqual(data['documents'][0]['sha256'],digest)
  self.assertFalse(data['grants_execution']);self.assertFalse(data['authorization_evaluated'])
  self.assertTrue(data['requires_source_review'])

 def test_explicit_current_and_correction_headings_require_review(self):
  headings=('当前','当前状态','当前进度','最新纠正','最新状态','最新进展','更正','纠正','修正','Current','Current Status','Correction','Corrections','Latest Update')
  for heading in headings:
   with self.subTest(heading=heading):
    data,_=self.call('# 当前\n待核对。\n## 历史\n旧记录。\n## '+heading+'：新判断\n不能只沿用前段。')
    self.assertEqual(data['status'],'detail_required')
    self.assertIn('history_followed_by_current_heading',data['detail_reasons'])
    self.assertEqual(data['documents'][0]['structural_conflicts'][0]['line'],5)

 def test_post_history_fenced_examples_do_not_trigger_conflict(self):
  for fence in ('```','~~~'):
   with self.subTest(fence=fence):
    data,_=self.call('# 当前\n待核对。\n## 历史\n'+fence+'text\n## 最新更正\n示例，不是当前判断。\n'+fence+'\n旧记录结束。')
    self.assertEqual(data['status'],'review_required')
    self.assertEqual(data['documents'][0]['structural_conflicts'],[])
    self.assertNotIn('示例',data['documents'][0]['text'])
 def test_without_history_boundary_all_current_text_remains(self):
  data,_=self.call('# 当前\n待核对。\n## 最新更正\n停止，不得重发。')
  self.assertEqual(data['status'],'review_required')
  self.assertIn('停止，不得重发。',data['documents'][0]['text'])
  self.assertFalse(data['documents'][0]['history_omitted'])
 def test_approval_layout_is_not_interpreted_or_shortened(self):
  p=self.work/'APPROVAL.md';p.write_text('## 历史\n旧许可。\n## 当前\nclosed，不得执行。',encoding='utf-8')
  data,_=self.call('当前任务只读。','--approvals','APPROVAL.md')
  d=next(d for d in data['documents'] if d['kind']=='approvals')
  self.assertEqual(data['status'],'review_required')
  self.assertEqual(d['text'],p.read_bytes().decode('utf-8'))
  self.assertFalse(data['authorization_evaluated'])
 def test_recovery_conflict_removes_all_excerpt_text(self):
  p=self.work/'RECOVERY.md';p.write_text('# 恢复\n旧下一步。\n## 历史\n旧记录。\n## 更正\n停止。',encoding='utf-8')
  before=p.read_bytes();data,_=self.call('当前状态需核对恢复记录。','--recovery','RECOVERY.md')
  self.assertEqual(data['status'],'detail_required')
  self.assertTrue(all('text' not in d for d in data['documents']))
  self.assertEqual(p.read_bytes(),before)
  self.assertEqual(next(d for d in data['documents'] if d['kind']=='recovery')['structural_conflicts'][0]['line'],5)
 def test_conflict_pointer_is_bounded_to_first_occurrence(self):
  data,_=self.call('# 当前\n旧。\n## 历史\n旧。\n'+'## 最新更正\n应回源。\n'*50)
  self.assertEqual(data['status'],'detail_required')
  self.assertEqual(len(data['documents'][0]['structural_conflicts']),1)
  self.assertEqual(data['documents'][0]['structural_conflicts'][0]['line'],5)

if __name__=='__main__':unittest.main()
