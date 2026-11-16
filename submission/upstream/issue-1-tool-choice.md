# Bug report: `tool_choice` is sent as a JSON object, which strict OpenAI-compatible servers reject

**Version:** `openminion==0.1.22`
**Provider:** `custom-openai-compatible` (`--api-format openai-compatible`) against `llama.cpp` b12425
**Where:** every turn that carries tools

## What happens

Requests to the provider include `tool_choice` as a **JSON object**. `llama-server`
answers every such request with:

```
W Wrong type supplied for parameter 'tool_choice', using default value:
  [json.exception.type_error.302] type must be string, but is object
```

`llama.cpp` is lenient: it falls back to its default and the turn completes. A
strict server (or a gateway that validates the OpenAI schema) answers `400`, and
the failure surfaces from the SDK only as a generic provider error, with no hint
that the request body itself was invalid.

## Evidence

Recorded with a pass-through proxy that logs request shape (no message text):

```json
{"path": "/v1/chat/completions", "bytes": 7631, "messages": 3,
 "system_chars": 5418, "tools": 1, "tool_choice": "dict"}
```

`tool_choice` is a `dict` on 3 of the first 4 requests of a single audit. The
server log shows the matching warning once per request.

## Expected

`tool_choice` should be the string form (`"auto"`, `"none"`, `"required"`) unless a
specific named function is intended, in which case the nested
`{"type": "function", "function": {"name": ...}}` shape is correct and
`llama.cpp` still rejects it — so a provider capability flag would be the safer
fix than changing the shape unconditionally.

## Why it matters for this hackathon

The hackathon asks builders to run a real model-backed agent. Running without a
hosted provider means an OpenAI-compatible local server, and the first thing a
builder sees in the server log is this warning. It reads like their setup is
broken. A one-line capability check in the OpenAI adapter would remove a whole
class of "is my endpoint wrong?" support questions.

## Minimal reproduction

```bash
llama-server -m qwen3-4b-q4.gguf --port 8080 --jinja
export OPENAI_COMPATIBLE_API_KEY=local
openminion setup --provider custom-openai-compatible --api-format openai-compatible \
  --base-url http://127.0.0.1:8080/v1 --model qwen3-4b --no-chat
python - <<'PY'
from openminion.api import Agent
print(Agent(instructions="say OK", tools=[], name="probe").run("say OK").text)
PY
grep -a "tool_choice" llama-server.log | tail -3
```
