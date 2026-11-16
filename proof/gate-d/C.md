# 作品 C

<!-- 以下是一个 Hackathon 提交仓库的 README 前 120 行。只按你看到的判断，不要推测作者。 -->

# TokenGuard Minion

A token-safety checker agent built on the **OpenMinion 0.1 SDK**
(Cortensor Hackathon #5).

Give it a chain and a token contract address; it cross-examines three free
public data sources, applies an explicit scoring rubric, and produces a
structured verdict — `SAFE` / `CAUTION` / `DANGER` with a 0–100 risk
score — plus a plain-language Markdown brief that is only written to disk
after passing an approval gate.

```
$ python -m tokenguard.cli bsc 0x55d398326f99059fF775485246999027B3197955 --auto-approve yes

=== TokenGuard verdict: SAFE (risk 5/100) ===
Tether USD (USDT) on chain 56
Positives:
  - Not flagged as honeypot by GoPlus or honeypot.is
  - Buy tax 0%, sell tax 0%, transfer tax 0%
  - Open-source verified contract
  - Deep liquidity: ~$39.1M in deepest PancakeSwap pair
  - Price on peg at $0.9992, FDV ~$9.18B
Brief saved: True (out/56-55d398326f-…/brief-56-55d398326f.md)
```

No API keys are needed for the data sources (GoPlus, honeypot.is and
DexScreener are keyless). The only key you need is an LLM provider key for
OpenMinion itself. No wallet, no funds, no transactions — the agent only
reads public data.

## Quick start

```bash
git clone https://github.com/Klowor2002/tokenguard-minion
cd tokenguard-minion
scripts/setup.sh                 # venv + deps + (first time) provider setup hints

export GEMINI_API_KEY=<your key> # or whichever provider you configured
scripts/run_example.sh           # checks USDT on BSC, writes out/<run>/ artifacts
```

Setup keeps everything project-local (`OPENMINION_HOME=$PWD`,
`OPENMINION_DATA_ROOT=$PWD/.openminion`) so it never touches your default
OpenMinion profile. Tested with openminion **0.1.21** on Python 3.12.

### Usage

```bash
.venv/bin/python -m tokenguard.cli <chain> <contract-address> [--auto-approve ask|yes|no]
```

- `chain`: `bsc`, `ethereum`, `base`, `polygon`, `arbitrum`, or a numeric chain id
- `--auto-approve ask` (default) prompts before the brief is written;
  `yes` / `no` are for scripted runs and demos

Per run, under `out/<chain>-<address>-<timestamp>/`:

| File | Contents |
|---|---|
| `report.json` | The validated `TokenSafetyReport` (verdict, score, flags, facts) |
| `diagnostics.json` | Per-stage run ids, session ids, token stats, wall time, and which recovery path produced the report |
| `brief-*.md` | The Markdown brief — only if the write was approved |

Exit codes: `0` ok · `1` provider failure · `2` unrecoverable model output ·
`3` turn timeout.

Offline tests (API parsers + the report-recovery logic, no network):

```bash
.venv/bin/python -m unittest discover -s tests -v
```

## How it works — the SDK workflow

Four OpenMinion stages, one workflow (`tokenguard/agent.py`):

| Stage | SDK pieces | What it does |
|---|---|---|
| **Assessor** | `Agent` + 4× `@tool(min_scope="READ_ONLY", idempotent=True)` + `output_type` | Calls GoPlus (contract security flags), honeypot.is (buy/sell simulation), DexScreener (liquidity/volume/price) and a local verdict-memory tool; applies the scoring rubric; returns a pydantic-validated `TokenSafetyReport` |
| **Recovery** | `AgentOutputValidationError.raw_text`, typed errors | If the reply fails validation (prose-wrapped, truncated, or schema-drifted JSON — all observed live on relay-served models), the raw reply is kept forensically, a normalizing local extraction runs, a tool-less **formatter** `Agent` converts flattened facts into the schema, and a deterministic **harvester** rebuilds the report from whatever verdict the model left behind (JSON or prose). `ProviderError` / `TurnTimeoutError` are retried with backoff |
| **Brief-writer** | `subagent()` delegation | Turns the structured report into a ≤450-word Markdown brief. Output is sanity-checked — a tool-less subagent can return a runtime block notice as "successful" text — with one retry and a deterministic local renderer as fallback |
| **Publisher** | `@tool(dangerous=True)` + `forced_tools` + `approval_callback` | Saves the brief to disk. The callback is the only path to a write: it denies any tool other than `save_brief` and sanitizes the filename. The write's *side effect* is verified afterwards — `forced_tools` proved advisory on one provider (a run completed with 0 tool calls) — and a pre-approved (`--auto-approve yes`) write is then performed locally and recorded |

Two design details that mattered:

- **Tools return dicts, never JSON strings.** The runtime's freshness
  verifier scans tool outputs recursively for dated-evidence keys
  (`retrieved_at`); it cannot see inside a string, and the run's answer is
  replaced by a refusal. Every tool payload carries `retrieved_at` + `source`.
- **Memory is a tool, not a side channel.** Previous verdicts live in
  `state/verdicts.json` and are read back through the `previous_verdict`
  tool, so the assessor can say whether a re-check changed the verdict.

The scoring rubric is explicit and lives in the assessor's instructions:
honeypot ⇒ DANGER ≥ 90; sell-tax ≥ 25% +45; unverified source +15;
mintable +10; blacklist/pause +10 each; liquidity < $10k +20; no pair +15;
holders < 100 +10; verdict bands ≤24 SAFE, 25–59 CAUTION, ≥60 DANGER.

## Example runs (live, 2026-11-15)

| Token | Chain | Verdict | Recovery path | Notes |
|---|---|---|---|---|
| USDT `0x55d3…7955` | BSC | **SAFE** 5/100 | formatter | First check: 0% taxes, open source, ~$39M liquidity, on peg |
| USDT `0x55d3…7955` | BSC | **SAFE** 10/100 | harvest | Re-check: assessor cited the stored prior verdict ("consistent with prior TokenGuard check") |
| CAKE `0x0E09…1cE82` | BSC | **SAFE** | harvest (+ local brief) | Mintable under PancakeSwap governance, 1.9M holders, pair since 2023 |
| WBNB `0xbb4C…095c` | BSC | **SAFE** 3/100 | harvest | Canonical wrapped-native contract, 8.9M holders, $35M liquidity |

Every path in the table fired live at least once — the recovery pipeline
is not theoretical. Full artifacts are in [`examples/`](examples/) and
[`demo/TRANSCRIPT.md`](demo/TRANSCRIPT.md).

## Building Blocks Tested

- Custom `@tool` functions with `min_scope="READ_ONLY"` and `idempotent=True`
  (the default tool scope is confirmation-gated — wrong for read-only APIs)
- `@tool(dangerous=True)` + `approval_callback` + `forced_tools` for a
  genuinely gated write
- `output_type` structured outputs (pydantic) and the
  `AgentOutputValidationError` recovery surface (`raw_text`)
- `subagent()` delegation under a coordinator agent