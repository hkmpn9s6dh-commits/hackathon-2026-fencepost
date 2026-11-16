# The workflow, end to end

One audit is two agent turns and four deterministic detectors. Nothing else.

```
repository
   │
   ├── scan/docs.py     prose: README, docs/*.md  ── chunked, ranked
   ├── scan/project.py  pyproject: requires-python, dependencies
   ├── scan/code.py     AST: imports, env reads, add_parser() names
   │
   ▼
[1] propose        Agent("fencepost")  reads one document, offers quotes
   │                  └── quote_gate: verbatim or dropped
   ▼
[2] pair           detectors pair each promise with the implementation
   │
   ▼
[3] counter-read   subagent("fencepost-counter-reader")
   │                  └── rebuttal must carry a quote that satisfies the promise
   ▼
ledger.json + report.md + report.html      exit 0 / 1
```

## Turn 1 — propose

`fencepost/propose` gets one document (the highest-scoring chunks of one file, up
to 2,400 characters) and returns

```json
{"claims": [{"kind": "command", "quote": "`multi verify`", "value": "verify"}]}
```

The reply is parsed here, not by the SDK's `output_type` validator, so a malformed
reply costs one retry instead of a spin (see `docs/05-FINDINGS.md` §3 for why that
mattered).

Then `quote_gate.verify_quote` does the only thing that matters: `text.find(quote)`.
If the quote is not literally in the file, the claim dies and the reason is written
to `ledger.dropped_quotes`. The stored quote is always the file's own bytes, never
the model's copy.

## Turn 2 — counter-read

Every candidate the detectors flagged is sent to a child agent whose instructions
are one idea: **knock it down, or quote the line that already satisfies it.**

```json
{"items": [{"id": "…", "rebut": true, "reason": "…", "evidence": "…"}]}
```

A rebuttal is accepted only if `evidence` is a verbatim line, it mentions the
subject of the finding, and it is found in the repository. A rebuttal without
evidence is not a rebuttal — it is recorded in `ledger.rejected_rebuttals` and the
finding stands. That rule exists because a 4B model produced a `rebut: true` whose
own prose confirmed the finding.

## Deterministic detectors

| Detector | Promise | Implementation |
|---|---|---|
| `pair_python_requires` | `Python 3.10+` in prose | `requires-python` in `pyproject.toml`, compared as version floors |
| `pair_dependencies` | the `dependencies = […]` table | top-level imports from AST, excluding stdlib, local modules and the package's own name |
| `pair_commands` | `` `mytool doctor` `` in prose | `add_parser("doctor")` anywhere in the tree |
| `pair_env` | `YOUR_API_KEY` in prose | `os.environ[...]`, `os.getenv(...)`, `environ.get(...)` |

None of them import the repository under audit. A `setup.py` never runs.

## What reaches the ledger

```json
{
  "run": {"mode": "model", "model": "qwen3-4b", "model_calls": 2,
          "model_failures": 0, "duration_seconds": 263.4, "run_id": "…"},
  "findings": [{"claim": {"file": "README.md", "line": 13, "quote": "multi verify"},
                "implementation": null, "verdict": "drift", "severity": "high"}],
  "dropped_quotes": [],
  "rejected_rebuttals": []
}
```

`fencepost explain <ledger> <id>` prints one finding with both sides and the verdict,
so a reviewer can argue with a single row without reading the whole report.
