"""Mechanical read-only current-prefix view, never an authorization decision."""
import re
from .resume import inspect_project,_read_document,MAX_BYTES

def _current_prefix(text):
    fence=None
    offset=0
    history_offset=None
    for number,line in enumerate(text.splitlines(keepends=True),1):
        marker=re.match(r'^ {0,3}(`{3,}|~{3,})',line)
        if marker:
            value=marker.group(1)
            if fence is None:fence=value
            elif value[0]==fence[0] and len(value)>=len(fence) and not line[marker.end():].strip():fence=None
        elif fence is None:
            if re.match(r'^#{1,6}\s+(?:历史(?:记录|入口|截止|接续|验收)?|History|Historical|Archive)(?:\s|[：:]|$)',line,re.I):
                if history_offset is None:history_offset=offset
            elif history_offset is not None and re.match(r'^#{1,6}\s+(?:当前(?:状态|进度)?|最新(?:更正|纠正|状态|进展)|更正|纠正|修正|Current(?: Status)?|Corrections?|Latest Update)(?:\s|[：:]|$)',line,re.I):
                # One pointer is enough to require source review; keep metadata bounded.
                return text[:history_offset].rstrip(),True,[{'code':'history_followed_by_current_heading','line':number}]
        offset+=len(line)
    return (text,False,[]) if history_offset is None else (text[:history_offset].rstrip(),True,[])

def inspect_brief(workspace,**kwargs):
    result=inspect_project(workspace,**kwargs)
    from pathlib import Path
    root=Path(workspace).absolute()
    for doc in result['documents']:
        if doc['truncated']:
            full=_read_document(root,doc['path'],doc['kind'],MAX_BYTES)
            if full['sha256']!=doc['sha256']:
                raise ValueError('checkpoint changed between brief reads')
            doc.update(full)
        text=doc['text']
        if doc['kind']=='approvals':doc['history_omitted']=False
        else:doc['text'],doc['history_omitted'],doc['structural_conflicts']=_current_prefix(text)
        doc['truncated']=False
        doc['excerpt_role']='literal_current_prefix_candidate' if doc['kind']!='approvals' else 'complete_approval_source_not_validated'
    size=sum(len(doc['text']) for doc in result['documents'])
    result['limits']['brief_excerpt_char_budget']=2000
    result['excerpt_chars_required']=size
    reasons=[]
    if size>2000:reasons.append('excerpt_budget_exceeded')
    if not result['documents'][0]['text'].strip():reasons.append('empty_current_prefix')
    if any(doc.get('structural_conflicts') for doc in result['documents']):
        reasons.append('history_followed_by_current_heading')
    needs_detail=bool(reasons)
    if needs_detail:
        for doc in result['documents']:
            doc.pop('text')
            doc['excerpt_unavailable']=True
    result.update(mode='read_only_project_brief',status='detail_required' if needs_detail else 'review_required',
                  authorization_evaluated=False,requires_source_review=True,grants_execution=False,detail_reasons=reasons,
                  reason='Open the source documents before continuing; excerpt capacity or source structure requires review.' if needs_detail
                         else 'Literal source view only; current intent, corrections and authority require review.')
    return result
