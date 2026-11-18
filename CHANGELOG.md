# Changelog

## 0.4.1 — literal brief and source-review boundaries

- Port the installed standalone ninnin 0.4.1 `resume --brief` behavior: a literal
  current-prefix view with full source fingerprints, intact approval records
  and a 2,000-character combined excerpt allowance.
- Return `detail_required` without source excerpts for an empty state prefix,
  excess excerpt size or recognized current/correction headings after history.
  Give a bounded first-conflict line hint; never infer execution permission.
- Preserve ordinary resume, v1 handoff formats, the legacy script/module names
  and the public Windows/macOS ancestor-alias portability correction.
- Include brief in doctor layout checks and use a single public module version
  for doctor reporting. This version is the standalone distribution revision,
  not the related workbench version.
- Expand English/Chinese explanations, result handling, API/compatibility docs
  and an offline synthetic late-correction example. Add brief regressions while
  retaining the existing suite; extend the existing CI workflow to run the demo.

No automatic checkpointing, semantic memory, model execution or native session
adapter is added. Source-selection tests do not establish agent obedience,
end-to-end continuation quality or measured token savings.

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
