# Not yet dead
your agent is crashed.It's not yet dead~

**Keep the work alive when an agent stops.**

[中文说明](README.zh-CN.md) · [Agent skill](SKILL.md) · [CLI reference](references/cli.md) · [MIT license](LICENSE)

Not yet dead turns saved task progress, the latest direction and real files
into a verifiable handoff for the next agent. Use it when a task is paused,
an agent exits unexpectedly, a conversation fills up, or you move work to
another model or platform.

It preserves what was saved: goals, decisions, completed and unfinished work,
unknowns, evidence and the next step. Unsaved internal state cannot be recovered.

## When the next agent needs a starting point

The draft is saved, the conversation stops, and the next agent needs to know:
**what is current, what was actually checked, and what must not be repeated?**
A long transcript or an old handoff alone does not answer that. Start from your
current project files, keep their source pointers, and compare any old bundle
without restoring it over newer work.

Use this small file-based tool when you already keep a `STATE.md` and want an
inspectable handoff without adopting a service or agent framework. It is not a
task scheduler, automatic memory collector or checkpointed execution engine.

**New in 0.4.1:** `resume --brief` shows a literal current-prefix candidate,
with full-source fingerprints and an explicit fallback to source review. It
does not summarize with a model or decide whether the next action is allowed.

## Quick start

Requires **Python 3.10 or newer**. The standalone CLI uses only the Python
standard library. No API key, model call, running desktop or pip install is
needed for file-based handoffs.

From the repository root:

```sh
python -B scripts/not_yet_dead.py doctor
python -B scripts/not_yet_dead.py resume --workspace examples/workspace --brief
python -B scripts/demo_brief.py
python -B scripts/demo.py
```

The demo uses a temporary copy of synthetic sample files, exports and verifies
a handoff, changes a current artifact, and confirms that `resume` reports the
change without restoring the old file.

## How the small view works

```text
Current STATE.md + recovery notes + approvals
    → validate paths, read and scan complete sources, fingerprint bytes
    → literal prefix before an explicit history heading (approvals stay whole)
    → review_required: read excerpts + check current intent and relevant sources
      detail_required: no excerpts; follow source paths and conflict line hints
    → continue only within actual authority; export a new cutoff only if needed
```

`demo_brief.py` creates synthetic temporary files and checks both outcomes. It
first returns `initial_status: review_required` and `history_omitted: true`.
After the demo appends a correction below history, it returns
`after_correction_status: detail_required`, `correction_line: 5` and
`grants_execution: false`. Both inspections leave their inputs unchanged;
only the demonstration itself writes the fixture.

| Result | What the reader should do |
| --- | --- |
| `review_required` | Read the literal candidate, check the current user instruction, approvals and relevant original evidence. Omitted history is not proven irrelevant. |
| `detail_required` | Read the current source region and any indicated conflict line, then follow related sources until the relevant stop, correction and authority questions are resolved. No excerpt is returned. |
| Nonzero exit | Address the reported missing, unsafe or changing input. Do not treat failure as an empty or verified project. |

The **2,000-character allowance covers all source excerpts together**, not JSON
metadata. Approval text is never shortened. Empty current state, oversized
excerpts or a recognized current/correction heading after history cause
`detail_required`. Heading recognition is deliberately narrow: unrecognized
layouts and corrections in ordinary prose may be missed; old historical
headings may conservatively trigger review. Neither status authorizes work.

Remove `--brief` for the existing wider `resume` view; `--max-chars` controls
that preview, not the brief allowance or complete-source safety scan. The tool
does not automatically load history into an agent or guarantee the agent follows
its pointers. See the [brief contract](references/brief.md) and
[Python API / compatibility](references/api.md).

## Install as an agent skill

Copy or clone this **whole directory** into a skill directory supported by your
agent, using the directory name `not-yet-dead`. Keep `SKILL.md`, `scripts/`,
`lib/` and `references/` together. Ask the agent to read `SKILL.md` and run
`doctor` through its terminal tool using the actual installation path.

An agent needs file access and Python execution to use the CLI. An agent with
only chat/file uploads can read a generated bundle but needs an external
execution environment to create or verify one. See [agent integration](references/agents.md).

The public project is named **Not yet dead**. Its original local skill name is
**ninnin**. Internal module names and v1 bundle identities remain compatible;
existing local installations do not need to be renamed.

## Commands

| Command | Purpose |
| --- | --- |
| `doctor` | Check the local installation and available entry points. |
| `resume` | Read current state, recovery notes and approvals; add `--brief` for the small literal view, or compare an old bundle with current artifacts. |
| `extract` | Export a portable bundle from saved JSON task/checkpoint records. |
| `verify` | Validate a bundle's structure, file inventory, sizes and SHA-256 hashes. |
| `export` | Export one persisted task from a compatible ninnin workbench Store. |
| `status` | List rooms in a compatible workbench Store. |

`resume` is read-only and does not start the task. `export` and `status` use the
legacy Store constructor, which can create/initialize a database and enable
WAL mode. Use them only on an explicitly selected compatible workbench data
root; use `resume` or `extract` for ordinary file projects.

Create a new handoff directory, then verify it:

```sh
python -B scripts/not_yet_dead.py extract --snapshot examples/snapshot.json --checkpoint examples/checkpoint.json --workspace examples/workspace --out /path/to/new-handoff
python -B scripts/not_yet_dead.py verify /path/to/new-handoff
python -B scripts/not_yet_dead.py resume --workspace /path/to/current-project --handoff /path/to/new-handoff
```

Replace the paths with real paths on your machine. Output directories must be
new; an existing bundle is never overwritten. Commands return JSON and use
nonzero exit status for failure. See the [input format](references/inputs.md).

## What a bundle contains

```text
handoff/
  handoff.md          # readable goals, direction, progress, unknowns and next step
  manifest.json       # version, cutoff, file inventory, sizes and hashes
  artifacts/          # selected artifact snapshots, preserving relative paths
  evidence/
    records.json      # saved public records and attachment provenance
```

The bundle keeps a historical cutoff. Later changes stay in the active
workspace; `resume` reports artifacts as `same`, `changed` or `missing`.
A hash match establishes byte identity, not the truth of a claim or authorship.

## Scope and limits

- The helper packages saved records; it does not automatically watch an agent,
  write checkpoints in the background, recover hidden reasoning or compress
  conversation history.
- The receiving agent checks the current user instruction, current files and
  existing approvals. A bundle does not grant new permission or reverse a pause.
- Known sensitive filenames, common credential patterns and private event
  fields are blocked or excluded. Review selected content before sharing;
  these checks are not a complete secret scanner or a sandbox.
- Native creation of a new conversation, message delivery and confirmation
  require an adapter to the receiving host. Bundle verification alone does
  not prove that another agent has taken over or completed a task.
- No general claim of improved agent accuracy, lower cost or reliable recovery
  of arbitrary tasks follows from the local file tests.

## Development

```sh
python -B -m unittest discover -s tests -t . -v
```

The suite uses temporary synthetic fixtures, without model requests or access
to real agent state. CI runs the suite on Windows, Linux and macOS. Local
verification and remote CI results should be reported separately.

See [CONTRIBUTING.md](CONTRIBUTING.md), [CHANGELOG.md](CHANGELOG.md) and
[NOTICE.md](NOTICE.md). Licensed under [MIT](LICENSE).
