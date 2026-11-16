# 作品 A

<!-- 以下是一个 Hackathon 提交仓库的 README 前 120 行。只按你看到的判断，不要推测作者。 -->

# Fencepost

**A local-first agent that audits the gap between what a repository promises and what it actually does.**

A fence is only as good as its posts. A README is only as good as the code behind
it. Fencepost reads both, pairs every promise with the line of code that is
supposed to keep it, and writes an evidence ledger where each row carries two
`file:line` citations — one for the promise, one for the reality.

Built for **Cortensor Hackathon #5** on the **OpenMinion 0.1 Python SDK**.

Use it the day you notice your README and your code disagree, or the week before
you ship: point it at a repository, get a ledger where every row is two
`file:line` citations and a verdict.

Here is a real run, unedited, against the deliberately broken fixture
`fixtures/multi`:

```console
$ fencepost audit fixtures/multi --no-model --yes
fencepost · multi
  2 promises survived the quote gate, 0 refused
  4 pairs to judge

  4 drift  ·  high 3  ·  refused quotes 0  ·  0.0s
   1. [high  ] README.md:13  multi verify
   2. [high  ] pyproject.toml:5  dependencies = ["httpx"]
   3. [high  ] README.md:5  Requires Python 3.11 or newer.
   4. [low   ] pyproject.toml:5  httpx
  written: fixtures/multi/fencepost-out/ledger.json
           fixtures/multi/fencepost-out/report.md
           fixtures/multi/fencepost-out/report.html
```

`--no-model` is the deterministic half: four detectors, no model, 0.2 s. Attach a
model and the same audit also asks it to propose quotes (each one checked
character by character) and hands the findings to a delegated counter-reader.
`docs/05-FINDINGS.md` records what that costs on a CPU-only 4B model.

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
export OPENAI_COMPATIBLE_API_KEY=...
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
