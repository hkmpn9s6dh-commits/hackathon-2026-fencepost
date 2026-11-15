# Fencepost

**A local-first agent that audits the gap between what a repository promises and what it actually does.**

A fence is only as good as its posts. A README is only as good as the code behind
it. Fencepost reads both, pairs every promise with the line of code that is
supposed to keep it, and writes an evidence ledger where each row carries two
`file:line` citations — one for the promise, one for the reality.

Built for **Cortensor Hackathon #5** on the **OpenMinion 0.1 Python SDK**.

---

## The one design decision everything else follows

A language model is allowed to *propose*. It is never allowed to *testify*.

Every quote a model offers must exist character-for-character in the file it
claims to come from. If it does not, the quote is thrown away and counted in the
ledger under `dropped_quotes`. The gate is 40 lines of code
(`src/fencepost/quote_gate.py`), it runs on every model output, and it is the
reason a small 4B model on a laptop CPU can produce a trustworthy audit.

The report prints the refusals. A tool that hides its own hallucinations is not
auditing anything.

## What it checks

| Kind | The promise | Where the reality is |
|---|---|---|
| `python_requires` | "Requires Python 3.11+" | `[project].requires-python` |
| `dependency` | "this is everything you must install" | top-level imports found by AST |
| `command` | "run `mytool doctor`" | `add_parser("doctor")` in the CLI |
| `env_var` | "set `OPENAI_API_KEY`" | `os.environ[...]` / `getenv(...)` |

Nothing is imported from the repository under audit. No `setup.py` runs, no
module-level side effect fires.

## Install

```bash
git clone <this repo> && cd fencepost
python3.11 -m venv .venv && . .venv/bin/activate
pip install -e .
```

Fencepost needs an OpenAI-compatible endpoint. Any of these work:

```bash
# a hosted provider
export OPENAI_COMPATIBLE_API_KEY=...        # or OPENAI_API_KEY for the openai preset
openminion setup --provider openai --model gpt-4.1-mini --no-chat

# or a local llama.cpp server, no key, no network
llama-server -m qwen3-4b-q4.gguf --host 127.0.0.1 --port 8080 -c 20480 --jinja
export OPENAI_COMPATIBLE_API_KEY=local
openminion setup --provider custom-openai-compatible \
  --api-format openai-compatible \
  --base-url http://127.0.0.1:8080/v1 --model qwen3-4b --no-chat
```

`OPENMINION_HOME` decides which config OpenMinion reads; Fencepost does not
change that, so a throwaway `export OPENMINION_HOME=$PWD/.om` keeps the audit
hermetic.

## Run

```bash
fencepost audit .                       # audit this repository
fencepost audit /path/to/repo --yes     # write the report without asking
fencepost audit . --no-model            # rules only, zero model calls
fencepost explain fencepost-out/ledger.json python_requires
```

Exit code is `0` when nothing at or above `--fail-on` (default `high`) was
found, `1` when something was. That makes it usable as a CI gate:

```yaml
- run: fencepost audit . --yes --fail-on high
```

## Output

```
fencepost-out/
  ledger.json    every finding, both citations, model provenance, refused quotes
  report.md      the table, for a PR comment
  report.html    the audit sheet, for a human
```

A finding is only counted when it survives three stages: the deterministic
detector pairs it, the reviewer model confirms it with surrounding context, and
a delegated **counter-reader** subagent fails to knock it down. Findings the
counter-reader rejects are listed separately and never counted.

## OpenMinion building blocks used

| Block | How Fencepost uses it |
|---|---|
| `Agent` + `output_type` | every model turn returns a pydantic model; malformed JSON is a typed error, not a guess |
| `@tool(min_scope="READ_ONLY")` | `read_lines` lets the reviewer pull real code when the snippet is not enough |
| `subagent()` | the counter-reader is a delegated child with its own instructions and output type |
| Sessions | one `session_id` per repository, so re-runs continue the same conversation |
| Diagnostics | `run_id`, `run_state`, `stats` are written into `ledger.json` per audit |

## Limits, stated plainly

- Four kinds of promise only. A promise Fencepost cannot check is not a promise
  it will pretend to check.
- Version comparison understands `>=`, `>`, `~=` and a bare `3.11`; it does not
  understand environment markers.
- On a CPU-only 4B model the whole audit takes minutes, not seconds.
- The report is evidence, not advice: it tells you where the two sides disagree,
  not which side you should change.

## License

Apache-2.0.
