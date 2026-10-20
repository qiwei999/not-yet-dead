# Contributing

Describe the concrete failure or use case, the expected behavior and a minimal
synthetic example. Keep real project records, credentials and conversations out
of reports and fixtures.

Use Python 3.10+ and run:

```sh
python -B -m unittest discover -s tests -t . -v
python -B scripts/demo.py
```

Keep standalone file commands free of host SDK and model-client dependencies.
Preserve v1 compatibility or explicitly version a format change. Use temporary
fixtures for behavioral changes, including path scope, altered packages,
checkpoint provenance and read-only resumption. Distinguish bundle integrity,
current workspace identity and content correctness in documentation and tests.

A new agent adapter should use that host's documented native interface and
report the exact level tested. Do not infer full integration from a successful
CLI subprocess. Do not add telemetry or background model requests implicitly.
