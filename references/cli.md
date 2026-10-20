# CLI reference

Run `python -B <skill-dir>/scripts/not_yet_dead.py <command>`. The compatibility
script `scripts/ninnin.py` exposes the same commands. Use quoted absolute paths
when the agent's current working directory is different. Successful commands
print JSON; argument errors and operational failures return a nonzero status.

## doctor

```text
not_yet_dead.py doctor
```

Checks Python, importable handoff/resume core, required files and commands.
Does not initialize a Store, create a project, contact a model or repair the
installation. Its `standalone_revision` is the independent skill revision.

## resume

```text
not_yet_dead.py resume --workspace <directory> [--state STATE.md] [--recovery <relative-file>] [--approvals DECISIONS.md] [--handoff <exact-old-bundle>] [--max-chars 8000]
```

Requires an existing state file. Recovery search is limited to
`recovery/RECOVERY.md` and `reports/recovery/RECOVERY.md`; if both exist choose
one explicitly. Missing recovery/approval files are reported as optional
unknowns. Paths are restricted to the selected workspace. Linked/reparse-point
paths and hardlinked checkpoint inputs are rejected.

JSON includes `documents` with original text, role, source path, bytes, full
SHA-256, character count and `truncated`; `missing_optional`; a verified
historical cutoff when selected; and artifact `comparisons`.
`grants_execution` is always false, and original text is returned as data.
Current user authorization remains the authority for actual work.

Each original file is limited to 1 MiB. Text defaults to 8,000 characters per
file, configurable from 256 to 16,000; hashes cover all bytes even if the text
is truncated. At most 128 historical artifact entries are compared. Binary
artifacts are compared as bytes, not decoded as project instructions.

The command does not write the workspace, restore missing files, pick the
newest bundle, run tests, open a database or start a model.

## extract

```text
not_yet_dead.py extract --snapshot <json-file> --out <new-directory> [--checkpoint <json-file>] [--workspace <artifact-root>]
```

Reads UTF-8 JSON (a BOM is accepted), captures saved facts and copies selected
artifacts/evidence. Attachments require a workspace. The output is staged,
verified and then published as a new directory; an existing destination is
refused. Changed, missing, duplicate, disallowed or hash-mismatched attachments
cause failure instead of a partially published bundle.

See [inputs](inputs.md) for fields and [handoff format](handoff.md) for output.

## verify

```text
not_yet_dead.py verify <bundle-directory>
```

Validates v1 shape, allowed paths, complete inventory, required directories,
byte sizes, SHA-256 and agreement between manifest facts and saved records.
Rejects unindexed files, missing files, duplicate JSON keys and unsupported
formats. It never executes attachments. The returned JSON is the manifest.

## Workbench compatibility

```text
not_yet_dead.py export --root <workbench-root> --task <task-id> --out <new-directory>
not_yet_dead.py status --root <workbench-root>
```

These commands instantiate the existing ninnin Store. The constructor creates
missing root directories/schema and sets SQLite WAL mode; do not describe these
commands as wholly read-only. They require explicit selection of a compatible
workbench data root. `export` reads the selected task, its related events and
saved checkpoint, using `workspaces/<task-id>` for attachments. `status` returns
the stored rooms, not a live model/process health report.

There is no worker launch, model call, session creation or API server command
in this standalone CLI.
