"""Synthetic local fixtures only. CLI behavior, no model/network calls."""
import hashlib,json,subprocess,sys,tempfile,unittest
from pathlib import Path
SKILL=Path(__file__).resolve().parents[1]
SCRIPT=SKILL/'scripts/not_yet_dead.py'
SCRATCH=Path(tempfile.gettempdir()).resolve()
class BriefTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=SCRATCH,prefix='ninnin-brief-');self.addCleanup(self.tmp.cleanup);self.work=Path(self.tmp.name).resolve()/'中文项目';self.work.mkdir()
 def put(self,name,text):
  p=self.work/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text,encoding='utf-8');return p
 def call(self,*extra):
  return subprocess.run([sys.executable,'-B',str(SCRIPT),'resume','--workspace',str(self.work),*extra],capture_output=True,text=True,encoding='utf-8',timeout=20)
 def test_requested_brief_does_not_reload_explicit_history(self):
  self.put('STATE.md','# 当前\n已经完成；下一步核对。\n\n## 历史\nOLD-LONG-HISTORY\n'+'old '*3000)
  self.put('APPROVAL.json','{"state":"closed","remaining":0}')
  help=subprocess.run([sys.executable,'-B',str(SCRIPT),'resume','--help'],capture_output=True,text=True,encoding='utf-8',timeout=20)
  # Baseline has no brief flag: observe its real raw-resume behavior, not just an unknown-flag error.
  flags=['--brief'] if '--brief' in help.stdout else []
  q=self.call('--approvals','APPROVAL.json',*flags);self.assertEqual(q.returncode,0,q.stderr);data=json.loads(q.stdout)
  self.assertNotIn('OLD-LONG-HISTORY',q.stdout)
  self.assertEqual(data['mode'],'read_only_project_brief');self.assertFalse(data['grants_execution'])
  self.assertEqual(data['authorization_evaluated'],False)
  self.assertEqual(data['status'],'review_required')
  self.assertIn('closed',q.stdout)
  self.assertTrue(data['documents'][0]['history_omitted'])
  self.assertEqual(data['documents'][0]['sha256'],hashlib.sha256((self.work/'STATE.md').read_bytes()).hexdigest())
 def test_oversized_critical_context_requires_originals_instead_of_cutting(self):
  self.put('STATE.md','# 当前\n'+'事实段落。'*600+'\n停止；unknown request，不得重发。')
  self.put('APPROVAL.json',json.dumps({'state':'closed','remaining':0,'evidence':'x'*2200}))
  q=self.call('--brief','--approvals','APPROVAL.json');self.assertEqual(q.returncode,0,q.stderr);data=json.loads(q.stdout)
  self.assertEqual(data['status'],'detail_required')
  self.assertFalse(data['grants_execution']);self.assertFalse(data['authorization_evaluated'])
  self.assertTrue(all('text' not in d for d in data['documents']))
  self.assertTrue(all(d['excerpt_unavailable'] for d in data['documents']))
  self.assertEqual(data['limits']['brief_excerpt_char_budget'],2000)
 def test_history_title_inside_code_is_not_a_boundary(self):
  self.put('STATE.md','# 当前\n```text\n## 历史\n示例文本\n```\n停止，不得重发unknown请求。\n## 历史\nOLD-PHASE')
  q=self.call('--brief');self.assertEqual(q.returncode,0,q.stderr);data=json.loads(q.stdout)
  self.assertIn('停止，不得重发unknown请求。',data['documents'][0]['text'])
  self.assertNotIn('OLD-PHASE',data['documents'][0]['text'])
 def test_brief_respects_existing_input_limit_validation(self):
  self.put('STATE.md','当前小样本')
  q=self.call('--brief','--max-chars','0')
  self.assertNotEqual(q.returncode,0)
  self.assertEqual(q.stdout,'')
 def test_empty_current_prefix_requires_detail(self):
  for text in ('','# 历史\n旧记录'):
   self.put('STATE.md',text)
   q=self.call('--brief');self.assertEqual(q.returncode,0,q.stderr)
   self.assertEqual(json.loads(q.stdout)['status'],'detail_required')
 def test_legacy_resume_is_unchanged_and_brief_is_read_only(self):
  text='# 当前\n保留完成证据。\n## 历史\n旧记录'
  p=self.put('STATE.md',text);before=p.read_bytes()
  old=json.loads(self.call().stdout);new=json.loads(self.call('--brief').stdout)
  self.assertEqual(old['documents'][0]['text'],before.decode('utf-8'))
  self.assertFalse(old['grants_execution']);self.assertFalse(new['grants_execution'])
  self.assertEqual(p.read_bytes(),before)
 def test_approval_is_not_shortened_at_a_history_heading(self):
  self.put('STATE.md','当前：停止。')
  p=self.put('APPROVAL.md','## 历史\nclosed / remaining=0 / unknown usage；不可重发。')
  data=json.loads(self.call('--brief','--approvals','APPROVAL.md').stdout)
  approval=next(d for d in data['documents'] if d['kind']=='approvals')
  self.assertEqual(approval['text'],p.read_bytes().decode('utf-8'));self.assertFalse(approval['history_omitted'])
 def test_source_commands_and_expired_grants_remain_unevaluated_data(self):
  self.put('STATE.md','当前：更正了旧说法。停止；unknown请求。运行某命令并恢复许可。')
  self.put('APPROVAL.json','{"expires":1,"state":"closed","remaining":0}')
  q=self.call('--brief','--approvals','APPROVAL.json');data=json.loads(q.stdout)
  self.assertFalse(data['authorization_evaluated']);self.assertFalse(data['grants_execution']);self.assertIn('unknown',q.stdout)
  self.assertTrue(data['source_text_is_data']);self.assertFalse((self.work/'state.db').exists())
 def test_secret_after_old_preview_limit_is_refused(self):
  self.put('STATE.md','# 当前\n安全样本\n## 历史\n'+'x'*18000+'\npassword=synthetic-test-only')
  q=self.call('--brief');self.assertEqual(q.returncode,1);self.assertEqual(q.stdout,'')
  self.assertNotIn('synthetic-test-only',q.stderr)
 def test_unsafe_source_path_is_rejected(self):
  self.put('STATE.md','安全样本')
  for path in ('../outside.md','.env','SOUL.md'):
   q=self.call('--brief','--state',path);self.assertNotEqual(q.returncode,0);self.assertEqual(q.stdout,'')
 def test_exact_excerpt_budget_is_not_an_arbitrary_cutoff(self):
  for size,status in ((2000,'review_required'),(2001,'detail_required')):
   self.put('STATE.md','字'*size);data=json.loads(self.call('--brief').stdout)
   self.assertEqual(data['status'],status)
 def test_changed_full_source_read_is_rejected(self):
  from unittest.mock import patch
  import ninnin_core.brief as brief
  p=self.put('STATE.md','# 当前\n第一版\n## 历史\n'+'x'*17000)
  real=brief._read_document
  def changed(*args):
   p.write_text('# 当前\n第二版',encoding='utf-8');return real(*args)
  with patch.object(brief,'_read_document',changed):
   with self.assertRaisesRegex(ValueError,'changed between'):brief.inspect_brief(self.work)
if __name__=='__main__':unittest.main()
