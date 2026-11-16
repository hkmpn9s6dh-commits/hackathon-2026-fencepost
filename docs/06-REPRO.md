# Repro notes

Everything in `docs/05-FINDINGS.md` can be re-observed with the steps below.
Nothing here needs a key, an account, or a GPU.

## Environment this was measured on

| | |
|---|---|
| OS | Windows 11 (10.0.26100) |
| Python | 3.12.14 (via `uv venv --python 3.12`) |
| openminion | 0.1.22 (PyPI) |
| Model server | `llama.cpp` b12425, `llama-b12425-bin-win-cpu-x64.zip` |
| Model | `Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf` (2.5 GB), CPU only, 12 threads |
| Provider | `custom-openai-compatible` → `http://127.0.0.1:8081/v1` (the recording proxy) |

## 1. Stand up the model server

```bash
curl -L -o llama.zip https://github.com/ggml-org/llama.cpp/releases/download/b12425/llama-b12425-bin-win-cpu-x64.zip
unzip llama.zip -d tools
curl -L -o models/qwen3-4b-q4.gguf \
  https://huggingface.co/bartowski/Qwen_Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen_Qwen3-4B-Instruct-2507-Q4_K_M.gguf
./tools/llama-server.exe -m models/qwen3-4b-q4.gguf \
  --host 127.0.0.1 --port 8080 -c 8192 --jinja -np 1 --alias qwen3-4b
```

## 2. Put the recorder in the middle

`tools/echo_proxy.py` forwards to the model server and appends one JSON line per
request: payload size, message count, system-prompt size, tool count, tool names,
`tool_choice` type and a system-prompt fingerprint. It stores no message text.

```bash
python tools/echo_proxy.py --listen 8081 --target http://127.0.0.1:8080 --log proof/proxy.jsonl
```

## 3. Point OpenMinion at the recorder

```bash
export OPENMINION_HOME=$PWD/.om OPENMINION_DATA_ROOT=$PWD/.om/data
export OPENAI_COMPATIBLE_API_KEY=local
openminion setup --provider custom-openai-compatible --api-format openai-compatible \
  --base-url http://127.0.0.1:8081/v1 --model qwen3-4b --no-chat
```

## 4. Observe the four findings

```bash
fencepost audit fixtures/ghost-env --yes --out out/ghost      # one promise, two turns
python - <<'PY'
import json
for line in open("proof/proxy.jsonl"):
    d = json.loads(line)
    print(d["bytes"], "system_chars=", d["system_chars"], "tools=", d["tools"],
          "tool_choice=", d["tool_choice"], "system_sha=", d.get("system_sha"))
PY
grep -a "Wrong type supplied for parameter 'tool_choice'" llama-server.log | tail -3
```

What you should see:

- `tool_choice=dict` on requests that carry tools → the `W Wrong type supplied…`
  warning in the server log (finding 2.1).
- `tools=1` on a request where Fencepost passed `tools=[]` (finding 2.2).
- Different `system_chars` within one turn, and one turn producing three or four
  requests (finding 2.3).
- Two requests with identical `bytes` and `system_sha` back to back (finding 2.4).

## 5. The `openminion run` session error (observed once)

```bash
export OPENMINION_HOME=$PWD/.om2 OPENMINION_DATA_ROOT=$PWD/.om2/data
openminion setup --provider custom-openai-compatible --api-format openai-compatible \
  --base-url http://127.0.0.1:8080/v1 --model qwen3-4b --no-chat
openminion run "hello"
# openminion: internal error: ValueError: Session 'cli-run' belongs to target
#  'api-user', not 'cli-user'
```

The mechanism is in `src/openminion/cli/commands/run.py` (hardcoded `cli-run` and
`cli-user`) plus `modules/storage/runtime/session_store/sessions.py:68` (refuses a
reused session id whose target differs). I could not reproduce it from a second
clean home, so treat it as "one confirmed instance, cause identified in source".
