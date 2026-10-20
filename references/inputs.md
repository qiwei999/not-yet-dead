# Saved task input

For ordinary file projects use `extract`. The snapshot must identify a task:

```json
{
  "task": {
    "id": "demo-task",
    "title": "Prepare a report",
    "state": "paused",
    "original_goal": "Prepare a reviewable report",
    "latest_direction": "Check the saved draft before further editing",
    "artifacts": [{"path": "STATE.md", "approved": true}]
  },
  "events": [],
  "events_cursor": null
}
```

Use project-owned IDs and facts from actual saved records. Task `version`,
`generation`, run metadata and event sequences are optional; omit or use null
where supported when unknown. Do not invent workbench identifiers or timestamps.

An optional checkpoint is either a data object or an envelope with `task_id`,
`generation`, `version`, `cutoff`, `created_at`/`timestamp` and `data`. Its task
identity must match. Checkpoint generations and event cutoffs cannot come from
a future snapshot. `cutoff` may be a sequence or `{"event_seq": 7}`.

The supported summary fields in checkpoint data are:

- `original_goal`, `latest_direction`, `route`, `decisions`;
- `completed`, `verified`, `changed`, `not_done`;
- `risks`, `unknowns`, `pending_confirmations`, `environment`;
- `verification`, `next_steps` and `unconfirmed_side_effects`.

Saved assertions under `verified` are preserved claims, not tests rerun by the
exporter. If nothing was verified, use an empty list and explain what is unknown.

`artifacts` and `evidence_files` may be listed on the task or in saved checkpoint
data. Each item is a workspace-relative path or an object with `path`, optional
`approved` and optional `sha256`. Explicit `approved: false` is rejected. Select
only files permitted for transfer. Do not list the same destination twice.

If an expected `sha256` is supplied, calculate it from the actual saved file;
a mismatch aborts export. Do not insert a placeholder checksum. A checkpoint
attachment is marked bound to the historical cutoff only when it supplies a
matching hash and the checkpoint has an event sequence. Other attachments are
explicitly export-time copies, not proof of their bytes at an earlier moment.

Public saved evidence may include command, exit status, output, source URL and
timestamp fields. Private/reasoning event kinds and unrelated task events are
excluded. Structured credentials, common secret text and known identity or
credential filenames are refused. This is pattern-based screening, not complete
privacy review. Keep unselected personal records outside the input.

`examples/` contains only synthetic sample data and can be used with the commands
in the README without substituting real private project files.
