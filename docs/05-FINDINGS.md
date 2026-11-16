# Building Blocks Tested · What We Learned

Everything below was observed while building Fencepost against `openminion==0.1.22`
on Windows 11, Python 3.12.14, with `llama.cpp` b12425 serving
`Qwen3-4B-Instruct-2507-Q4_K_M` on CPU as the OpenAI-compatible provider.

Where I could only see something through an instrument of my own making, I say so,
and I say what changed when the instrument turned out to be wrong (§3).

---

## 1. What worked, and was pleasant

| Block | What I did | Result |
|---|---|---|
| `Agent` | every model job is one `agent.run(...)` with `instructions` and a `session_id` | predictable; a failed turn raises instead of hanging |
| `subagent()` | the counter-reader is a delegated child with its own instructions | child shares the parent runtime, so no second config; lineage and timeout behaved as documented |
| Sessions | one `session_id` per repository | a repeat audit resumes the same conversation |
| `AgentRunResult.stats` | read `input_tokens`, `output_tokens`, `llm_calls`, `tool_calls`, `duration_ms` | the single most useful thing in the SDK for a tool that has to explain its own cost — it is what `ledger.json` records |
| `run_id` / `run_state` | written next to every audit | makes a ledger traceable to the turn that produced it |
| `@tool(min_scope="READ_ONLY")` | `read_lines` lets a reviewer pull real code | works; declaring the scope removes the confirmation prompt as documented |

## 2. What did not work

### 2.1 `tool_choice` is sent as a JSON object; `llama.cpp` rejects the type

Every request that carries a tool also carries `tool_choice` as a JSON **object**.
`llama-server` logs, once per request:

```
W Wrong type supplied for parameter 'tool_choice', using default value:
  [json.exception.type_error.302] type must be string, but is object
```

`llama.cpp` is lenient and falls back to its default, so the turn completes. A
strict server or a schema-validating gateway will answer `400`, and from the SDK
that surfaces as a generic provider error with no hint that the request body was
invalid. **This one is independent of my instrumentation**: the warning is in the
server's own log.

### 2.2 A tool-free turn still sends `tool_choice`, and still advertises a tool

`Agent(tools=[])` is the documented way to run a turn with no tools. The request
body still contained `"tools": 1` and a `tool_choice` object, so the model is
offered a tool whose selector the server has already rejected.

Measured from request bodies captured by a pass-through recorder (request side is
trustworthy even though the recorder had a bug on the response side — see §3).

**Why it matters:** the point of `allowed_tools=[]` is prompt economy. Every extra
tool schema is prefill you pay for on every call, and on a CPU model prefill is
the whole budget.

### 2.3 One `agent.run()` is three or four provider calls

Measured from `AgentRunResult.stats`, not from my recorder: a turn that answered
with one word reported `"llm_calls": 4` and `"output_tokens": 106`. A turn that
returned a 60-token JSON object also reported 4. So the cost of a turn is not the
cost of one completion — it is three to four of them, and each one re-sends the
system prompt (5.4k–9.7k characters across the calls of a single turn, measured
from request bodies).

On a 12-thread CPU at ~45 prompt tokens/s, that is ~40 s per call, which is why a
two-turn audit takes four minutes and a five-turn audit takes fifteen. On a hosted
model this is a bill; on a local model it is the difference between a demo and a
coffee break.

### 2.4 `openminion run` can die with an internal error after a config change

Observed once, on a fresh `OPENMINION_HOME` that had just been configured with
`setup --provider custom-openai-compatible`:

```
openminion: internal error: ValueError: Session 'cli-run' belongs to target
 'api-user', not 'cli-user'
```

The mechanism is in the source: `cli/commands/run.py` hardcodes
`session_id = "cli-run"` **and** `target = "cli-user"`, while the session store
(`modules/storage/runtime/session_store/sessions.py:68`) refuses to reuse a
session id whose target differs. Any other surface that ever created a session
called `cli-run` poisons `openminion run` permanently, with an error that names
neither the session's origin nor a way out.

I could not reproduce it from a second clean home, so this is **one confirmed
instance with the mechanism identified in source**, not a confirmed regression.
Repro attempt and a candidate patch are in `docs/06-REPRO.md` and
`submission/upstream/`.

## 3. What I got wrong while measuring (and how I noticed)

My first instrument was a 90-line recording proxy between OpenMinion and
`llama-server`. Its handler sent `Content-Length` twice — once copied from the
upstream response headers, once appended. The first request through it succeeded;
every later request on the same keep-alive connection stalled. OpenMinion waited,
my turn budgets expired, and I spent an hour concluding that the SDK had a retry
loop.

Two things gave it away: the stalls were always on the *second* request of a turn,
and removing the proxy from the path cut a propose turn from "never finishes" to
**81 s**. The duplicate-request pattern I had written down as a finding disappeared
with the same fix, so it is not in this report.

The lesson is not "proxies are hard". It is that a tool which reports on another
tool's cost has to be able to prove its own numbers — which is the same rule
Fencepost applies to a model's quotes. My recorder now writes request sizes only,
and the numbers in §2.3 come from the SDK's own `stats`, not from the recorder.

## 4. What this means for the product

The typed layer is good: `stats`, `run_id`, and `subagent` are what made a 4B model
on a laptop usable for a job that needs trustworthy output. The cost layer is where
the work is: **one turn is several provider calls, each carrying a large and
unstable system prompt**. If OpenMinion wants local models to be a first-class path
— and "local-first" is the pitch — the next release should look at a stable prompt
prefix so the provider can cache it, an honest `tools: []`, and a string
`tool_choice` for providers that validate it.

---

## 5. The first repository it audited was this one

`scripts/verify.sh` ends with `fencepost audit .` (AC-14). The first time it ran,
it reported **three high drifts in this repository** — and two of them were the
tool's fault, not the docs'.

### 5.1 A specimen is not a promise (tool bug, fixed)

`README.md` documents its four detectors in a table whose cells quote examples:

```
| `env_var` | "set `OPENAI_API_KEY`" | `os.environ[...]` / `getenv(...)` |
| `python_requires` | "Requires Python 3.11+" | `[project].requires-python` |
```

The rule extractor read those cells as the repository promising those things, so
its own reference table became a drift. The fix is a distinction the tool should
have had from the start: **inline code inside a table row is a specimen, not a
promise.** Requirements belong in prose. Six unit tests in
`tests/test_extract_specimens.py`; the clean fixture now carries a reference table
so `verify.sh` fails if the rule regresses.

### 5.2 A placeholder is not a credential (tool bug, fixed)

`YOUR_API_KEY` has the shape of a credential and can never be read by any code
path, so it always produced a "documented but never read" finding. Now every
`YOUR_`/`MY_`/`EXAMPLE_`/`SAMPLE_`/`DUMMY_`/`FAKE_`/`PLACEHOLDER_`/`XXX_` prefix is
skipped as a blank to fill in. Found in the same self-audit.

### 5.3 One finding was true (docs bug, fixed)

The remaining drift was real. The install block had a trailing comment naming the
SDK preset's own key variable — a name this repository never reads, because the
`openai` preset inside the SDK reads it. The sentence promised something this code
does not keep, so the sentence went — not the detector. `fencepost audit .` now
reports **0 drift**, and the three findings above are why the number is
believable: a tool that reports zero on itself without ever having reported a true
positive on itself has not been tested.
