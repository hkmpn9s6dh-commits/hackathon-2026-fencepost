# 作品 B

<!-- 以下是一个 Hackathon 提交仓库的 README 前 120 行。只按你看到的判断，不要推测作者。 -->

# Veritas

Built for **Cortensor Hackathon #5**: a small, working agent on the OpenMinion 0.1 SDK.

![tests](https://github.com/faust-dark/veritas/actions/workflows/ci.yml/badge.svg)

Adversarial verification on the [OpenMinion](https://openminion.com) 0.1 SDK.

Veritas answers a question the way you'd want a *trusted* system to answer it:
not with a single model's say-so, but by making three agents argue it out and
handing you the evidence.

```
Question ──► Proposer ──► Critic ──► Judge ──► Verdict + evidence bundle
             (answers)     (attacks)  (rules)
```

All three are OpenMinion **subagents** sharing one runtime. Each returns a
**typed (structured) result**, and the run is recorded end-to-end so the final
output is an auditable evidence bundle, not a bare answer.

## Veritas and Corgent

[Corgent](https://docs.cortensor.network/community-and-ecosystem/products-and-agents/corgent)
is Cortensor's core trust & execution agent, the ERC-8004-native oracle that
delegates work to redundant miners and validates results with
PoI/PoUW, consensus, and node reputation. It is already built on the network.
Veritas does **not** reimplement Corgent. The two answer different questions
and are designed to be complementary:

| | Corgent | Veritas |
|---|---|---|
| Trust mechanism | network consensus + proof (redundant miners, PoI/PoUW) | adversarial reasoning (propose / critique / rule) |
| Question it answers | "was this computed consistently and within spec?" | "does this answer survive a hostile cross-examination?" |
| Verdicts | `VALID` / `INVALID` / `RETRY` / `NEEDS_SPEC` | `VERIFIED` / `REFUTED` / `UNCERTAIN` |
| Depends on | the Cortensor network (miners, sessions, validators) | any OpenMinion provider, even one local model |
| Output | proof signals (consensus, reputation, integrity) | an interpretable reasoning trail (objections that survived, rationale) |

In one line: **Corgent proves the answer was computed consistently by enough
miners; Veritas proves the answer survives hostile cross-examination.** Corgent
is the consensus; Veritas is the argument.

Between them sits **Bardiel**, Cortensor's product/UX agent (Virtual-first,
ERC-8004), built on top of Corgent. It orchestrates the higher-level workflow
a user-facing app runs (GAME/ACP flows, ecosystem presets) and delegates the
trust decision to Corgent.

They meet at the seam where reasoning runs out. When Veritas's Judge returns
`UNCERTAIN`, the case escalates up the ladder:

```
UNCERTAIN ──► Bardiel (product orchestration) ──► Corgent (network consensus)
```

`veritas.corgent.escalation_plan(case)` renders the full route as concrete
requests; `handoff(case)` returns just the Corgent `validate` request. The CLI
attaches the escalation plan to the report automatically on `UNCERTAIN`.

## Why this is interesting

- **Complementary, not a clone.** Veritas deliberately uses a *single* runtime
  and adversarial roles, not redundant miners; it fills the gap Corgent
  explicitly leaves open ("agents still think; Corgent helps them be sure").
  Veritas is the reasoning side; Corgent is the proof side.
- **Self-contained.** No external APIs, no database, no scraping. A single
  `python run.py verify` runs the whole pipeline on whatever OpenMinion
  provider you have configured.
- **Deep SDK use.** Delegation (`subagent`), structured output
  (`output_type` + Pydantic), session identity, and the public error types
  (`ProviderError`, `TurnTimeoutError`, `AgentOutputValidationError`) are all
  exercised on the happy path and the failure path.
- **Honest.** When the model can't decide, Veritas says `UNCERTAIN` instead of
  bluffing, and hands the case to Corgent's consensus layer instead of
  guessing.

## How it uses the OpenMinion SDK

The whole workflow is ~20 lines of SDK. One `Agent` context manager owns the
runtime; three `subagent()` children do the work; each declares an
`output_type` so the reply is decoded into a typed object:

```python
from openminion import Agent, subagent

with Agent(name="veritas-coordinator", tools=[]) as coordinator:
    proposer = subagent(coordinator, name="proposer",
                        instructions=PROPOSER_INSTRUCTIONS,
                        output_type=Claim, tools=[])
    claim = proposer.run(question, timeout_seconds=60).output      # typed Claim

    critic = subagent(coordinator, name="critic", instructions=CRITIC_INSTRUCTIONS,
                      output_type=Critique, tools=[])
    critique = critic.run(f"...{claim.model_dump_json()}").output  # typed Critique

    judge = subagent(coordinator, name="judge", instructions=JUDGE_INSTRUCTIONS,
                     output_type=Verdict, tools=[])
    verdict = judge.run(f"...{critique.model_dump_json()}").output  # typed Verdict
```

The SDK blocks in play: `Agent` (session identity + context manager),
`subagent` (delegation), `output_type` (structured output), `.run()` →
`AgentRunResult` (`.output`, `.run_id`, `.run_state`, `.session_id`), and the
public error types (`ProviderError`, `TurnTimeoutError`,
`AgentOutputValidationError`) handled around each stage.

## Quickstart

```bash
# 1. install the SDK and configure a provider
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
openminion setup            # pick cortensor, ollama, openai, ... (any provider)

# 2. sanity-check the runtime
openminion doctor --check-turn

# 3. run the pipeline (one bounded question)
python run.py verify "Is it true that humans only use 10% of their brains?"

# 4. write the report + evidence bundle to disk