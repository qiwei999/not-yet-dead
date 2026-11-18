# Brief view / 简报视图

`resume --brief` is an opt-in literal view of saved files, not a model summary,
authorization evaluator or execution-resume operation. Ordinary `resume` is
unchanged. Both use the same source validation and optional bundle comparison.

```sh
python -B scripts/not_yet_dead.py resume --workspace examples/workspace --brief
python -B scripts/demo_brief.py
```

## Selection, budgets and status

The reader first validates the workspace and reads `STATE.md`, optional recovery
notes and the selected approval source through `inspect_project`. Every source
is checked in full for size, sensitive paths, common secret patterns and changes
during a read. Files are UTF-8 (BOM accepted), at most 1 MiB each. If the normal
preview truncated a source, brief rereads it and requires the full SHA-256 to
match. This is not an atomic snapshot of all files or a filesystem sandbox.

For state and recovery text, brief takes a literal prefix before the first
recognized history heading. It keeps the entire selected approvals document,
without interpreting its headings or checking whether its permissions are valid.
When there is no recognized history boundary, all of the text is a candidate.

The sum of candidate source text must fit **2,000 Python string characters**.
This is not a token count or a bound on the JSON response, which also contains
paths, fingerprints, comparison metadata and status fields. `--max-chars` must
still be 256–16000 but does not change this allowance or bypass safety checks.

| `status` | Meaning |
| --- | --- |
| `review_required` | Candidate excerpts fit and no recognized structural conflict was found. They still need source/intent/authority review. |
| `detail_required` | No source `text` is returned; each document has `excerpt_unavailable: true`. Read the originals using their paths and any line hint. |

Both statuses return exit code 0 because inspection succeeded. Neither is
permission to execute. They keep `grants_execution: false`,
`authorization_evaluated: false` and `requires_source_review: true`. These fields
do not revoke existing authorization or demand mechanical reapproval.

`detail_reasons` can contain:

- `excerpt_budget_exceeded`: combined candidate text exceeds 2,000 characters.
- `empty_current_prefix`: required state candidate is empty or whitespace.
- `history_followed_by_current_heading`: a state/recovery source has a recognized
  current/correction heading after its history boundary.

A conflict suppresses **all** excerpts, not just the conflicting document. The
original `sha256`, `bytes`, `total_chars`, role and paths remain. The per-document
`structural_conflicts` contains at most the first matching conflict's `code` and
1-based `line`. This is a navigation hint, not a complete conflict inventory.
`excerpt_chars_required` describes candidate text size, not the full history size.

## Exact layout assumptions

Recognized history headings begin at column 1 with one to six `#`, whitespace,
then one of these names (case-insensitive for English):

- `历史`, `历史记录`, `历史入口`, `历史截止`, `历史接续`, `历史验收`
- `History`, `Historical`, `Archive`

After history, these current/correction names cause source review:

- `当前`, `当前状态`, `当前进度`
- `最新更正`, `最新纠正`, `最新状态`, `最新进展`, `更正`, `纠正`, `修正`
- `Current`, `Current Status`, `Correction`, `Corrections`, `Latest Update`

Names must be followed by whitespace, an ASCII/Chinese colon or line end.
Backtick/tilde fences of at least three characters (up to three leading spaces)
are skipped; a matching character and at least the opening length closes the
fence when no trailing text remains. This small scanner is **not a complete
Markdown parser**. Setext headings, indented headings, ordinary correction prose,
and other names are not guaranteed to be recognized. Old headings inside history
can trigger a conservative fallback; the scanner cannot determine factual recency.

## What to do with the result

Start with the current source region and the conflict line's neighborhood, then
follow related pointers until the authority, stop, unknown-side-effect and
correction questions relevant to the next action are clear. Do not automatically
reload every historical page; do not act from a prefix while a relevant conflict
remains unresolved. Sources and the current user conversation retain authority.

The CLI does not open these regions in an agent, enforce source reading, choose
the next step, restore an older artifact or prove improved agent obedience.
An omitted history section is not proof that its contents are irrelevant.

## 中文要点

- 这是机械字面视图；只在有限历史标题前取前缀，批准记录不裁剪，不判断批准是否有效。
- 2,000 字符只限制来源摘录合计，不限制整个 JSON，也不是 token 节省指标。
- `review_required` 仍须核对原件及当前意图；`detail_required` 不给旧前缀，按指针回源。
- 先定点读当前段和冲突行附近，再补读相关证据；不强制整份历史重载，也不能忽略未排除的矛盾。
- 非标题纠正、其他排版可能漏掉；历史里的旧标题也可能触发。结构提示不证明纠正有效。
- 完整原件安全检查仍执行；成功退出、哈希相等、生成包成功都不代表新的执行许可或实际接手完成。
