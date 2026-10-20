# Changelog

## 0.3.0 — public portability correction

- Recognize equivalent absolute workspace paths through operating-system
  ancestor aliases, while retaining traversal, symlink/reparse-point and
  workspace-boundary checks.
- Normalize temporary fixture roots so native Windows short names and macOS
  `/var` aliases do not break path assertions or fault-injection callbacks.
- Add real-filesystem alias-path and protection regression coverage.

## 0.3.0 — initial public distribution

- Publish the ninnin standalone handoff skill as **Not yet dead**.
- Provide the `not-yet-dead` skill and `scripts/not_yet_dead.py`, retaining
  `scripts/ninnin.py`, the internal module name and the v1 package format.
- Include `doctor`, read-only `resume`, `extract`, `verify` and the compatible
  workbench `export` / `status` commands.
- Add generic English/Chinese instructions, synthetic examples, portable
  inherited tests and a cross-platform CI workflow.

This distribution does not install or rename an existing local skill, add
background checkpointing, or implement native session adapters for other hosts.
