# Fencepost — submission sheet

**Cortensor Hackathon #5 · OpenMinion 0.1 Python SDK · individual entry**

| | |
|---|---|
| Project | **Fencepost** — a local-first contract-drift auditor agent |
| Repository | `hkmpn9s6dh-commits/hackathon-2026-fencepost` (public) |
| Demo video | `submission/fencepost-demo.mp4` (length and beats in `docs/03-VIDEO.md`) |
| Model used in the demo | `Qwen3-4B-Instruct-2507-Q4_K_M` on CPU via `llama.cpp`, no key, no GPU |
| Entry type | solo, free, online |

## One paragraph

Fencepost reads a repository's prose and its code and reports where the two
disagree: a README that promises Python 3.10 while `requires-python` says 3.11, a
documented command no `add_parser()` ever registered, a credential the docs tell
you to set that no code path reads, an import that the dependency table never
declares. Every finding is two `file:line` citations and one verdict. A language
model is allowed to **propose** that a sentence is a promise, but the proposal only
becomes evidence if the exact quote is found, character for character, in the file
it claims to come from. The refusals are printed.

## The five things the brief asks for

| Asked for | Where it is |
|---|---|
| Public repo + README with setup and run instructions | `README.md` — install, configure a provider (hosted or local), `fencepost audit .` |
| A short explanation of the OpenMinion SDK workflow | `README.md` §"OpenMinion building blocks used"; `docs/01-WORKFLOW.md` |
| One working example + a 1–5 minute demo | `fixtures/` (six deliberately broken repositories) + `submission/fencepost-demo.mp4` |
| **Building Blocks Tested** | `docs/05-FINDINGS.md` §1–2 |
| **What We Learned** | `docs/05-FINDINGS.md` §3–4 |

## How it runs (three commands)

```bash
pip install -e .
openminion setup --provider openai --model gpt-4.1-mini --no-chat     # or a local llama.cpp endpoint
fencepost audit . --yes
```

`--no-model` gives the deterministic four-detector audit with no provider at all,
which is what `scripts/verify.sh` uses so a judge can check the tool in 30 seconds.

## What the SDK is doing, in one table

| Turn | Agent | Building blocks |
|---|---|---|
| 1 | `fencepost` — reads one document, offers quotes that look like promises | `Agent`, `session_id`, `output_type` schema (`Proposals`), `stats` |
| 2 | `fencepost-counter-reader` — a delegated child whose only job is to refute each finding, with evidence, or not at all | `subagent()`, separate instructions and output schema |
| — | `read_lines` | `@tool(min_scope="READ_ONLY")` — the reviewer can open a file when the snippet is not enough (`--with-tools`) |

Every quote goes through `src/fencepost/quote_gate.py` before it can become a
claim; every rebuttal goes through the same kind of gate before it can remove one.

## Findings, in one line each

1. `tool_choice` is sent as an object; `llama.cpp` rejects the type on every request (visible in the server's own log).
2. A tool-free turn still advertises a tool and still sends `tool_choice`.
3. One `agent.run()` is 3–4 provider calls (`stats.llm_calls = 4` for a one-word answer), each re-sending a 5.4k–9.7k character system prompt — the whole cost of a local-model run.
4. `openminion run` can die with `Session 'cli-run' belongs to target 'api-user', not 'cli-user'`; mechanism identified in source, one confirmed instance.

Details, evidence, and the reproduction steps are in `docs/05-FINDINGS.md` and
`docs/06-REPRO.md`. Bug reports and a candidate patch are in `submission/upstream/`;
they are **not filed yet** — filing them is a public action on the maintainers'
tracker, so it waits for the account owner.

## Honest limits

- Four kinds of promise. Anything Fencepost cannot check, it does not claim to check.
- Version comparison understands `>=`, `>`, `~=` and bare `3.11`; not environment markers.
- On a CPU-only 4B model the full audit takes ~4–6 minutes; the video shows the real
  elapsed time rather than hiding it.
- The report is evidence, not advice.
