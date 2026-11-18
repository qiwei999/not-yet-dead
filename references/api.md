# Python API and compatibility

This is a source distribution, not a published pip package. Python 3.10+ and
the standard library are sufficient. Add the **selected distribution's** `lib`
directory to your import path; do not accidentally import another installation.
The CLI scripts already do this for their own adjacent `lib`.

Example from the repository root:

```python
from pathlib import Path
import sys

root = Path.cwd().resolve()  # run from this distribution's root
sys.path.insert(0, str(root / "lib"))
from ninnin_core.brief import inspect_brief
from ninnin_core.resume import inspect_project

brief = inspect_brief(root / "examples/workspace")
assert brief["grants_execution"] is False
print(brief["status"])
full = inspect_project(root / "examples/workspace")
assert full["mode"] == "read_only_project_resume"
```

## File interfaces

| Callable | Inputs | Result / side effects |
| --- | --- | --- |
| `ninnin_core.resume.inspect_project` | `workspace`, keyword-only `handoff=None`, `state='STATE.md'`, `recovery=None`, `approvals='DECISIONS.md'`, `max_chars=8000` | Dictionary of source documents and optional comparisons; does not write project files or create a Store. |
| `ninnin_core.brief.inspect_brief` | `workspace`, the same keyword arguments forwarded to `inspect_project` | Same source/comparison metadata plus brief status, excerpt roles, omission flags and detail reasons. Read-only; may reread truncated sources. |
| `ninnin_core.handoff.export_handoff` | `snapshot`, `checkpoint`, `output_dir`, `workspace=None` | New verified bundle `Path`; creates output parent/staging directories, refuses an existing output. |
| `ninnin_core.handoff.verify_handoff` | `path` | Validated manifest dictionary; never executes attachments. |
| `ninnin_core.cli.main` | `argv=None` (list of CLI arguments or process arguments) | Prints JSON for successful operations, returns 0; handled operational failures print error JSON on stderr and return 1. Argument parsing may raise `SystemExit`. |

Library errors are exceptions, not error dictionaries. Depending on the failure,
callers should handle `OSError` (including missing files and permission errors),
`ValueError` and `KeyError`; malformed API calls can also raise `TypeError`.
The library is not a network API or a running server. See [CLI](cli.md),
[brief output](brief.md) and [input formats](inputs.md) for validation details.

## Compatibility kept in 0.4.1

- Public display name: **Not yet dead**; repository/skill slug: `not-yet-dead`.
- Preferred CLI: `scripts/not_yet_dead.py`; legacy alias: `scripts/ninnin.py`.
- Python namespace: `ninnin_core`; no global rename or new command on PATH.
- Bundle schema: `schema_version: 1`, schema identity `urn:ninnin:handoff:v1`.
  Bundle layout, existing generated headings and field names are unchanged.
- Ordinary `resume` retains its existing wider preview. `--brief` is opt-in.
- The public workspace path fix remains: equivalent absolute ancestor aliases
  are rebased only at the workspace boundary; links inside it stay rejected.
- `export` and `status` retain compatible Store access, **including its possible
  database initialization/WAL side effects**. They are not file-only read APIs.
- The module version, `doctor` standalone revision and public skill version
  identify this distribution as `0.4.1`; they do not identify a workbench release.

No native session adapter, background worker, model provider, new REST server,
automatic message injection or live agent continuation is shipped or validated.
Receiving-host integrations require separate implementation and testing.

## 中文说明

优先使用随包 CLI；直接调用 Python 时，确认导入来自你选择的副本 `lib/ninnin_core`。
`inspect_brief` 返回小视图和回源状态，`inspect_project` 保留旧版普通预览；都不执行任务。
公开名、脚本别名、模块名和 v1 包格式分别保留兼容，不因版本更新全局改名。
工作台 `Store` 的兼容读写不等于发布工作台产品；任意 agent 的会话接续接口仍未验证。
