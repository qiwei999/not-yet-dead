# Portable handoff v1

The bundle layout is `handoff.md`, `manifest.json`, `artifacts/` and `evidence/`.
`evidence/records.json` is always present, and empty artifact/evidence directories
must survive transport. The machine-readable contract is
[`schemas/handoff-v1.schema.json`](../schemas/handoff-v1.schema.json).

The manifest stores task/run identity, direction version, source states,
checkpoint/event cutoff, a complete summary, unknown side effects, permissions
and a file inventory. The file inventory covers every other file, including
human notes and saved records, with size and SHA-256. It deliberately does not
hash itself. Saved records must agree with manifest facts.

A successful verifier establishes package consistency under this format. It
provides no signature or trusted authorship. An attacker who can replace the
whole bundle can construct another internally consistent bundle. Independently
check the source and the meaning of its contents.

The bundle preserves `execute: false` and `resume_requires_confirmation: true`
as compatibility markers. Treat them as absence of authority inside the
bundle, not as a revocation of approval already granted in the current user
conversation. A user pause still requires an explicit user continuation.

Keep a frozen bundle unchanged after export. Store later receipts separately
and update the active project state. When making a ZIP, include directory
entries as well as regular files; omit links and preserve canonical relative
paths. Verify after unpacking before use.

Three distinct questions need separate answers:

1. Is the bundle intact and internally consistent? Use `verify`.
2. Do its artifact bytes match the active workspace? Use `resume --handoff`.
3. Are its claims correct and has the receiving agent continued successfully?
   Inspect the original evidence and actual receiving results.
