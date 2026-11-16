# 作品 F

<!-- 以下是一个 Hackathon 提交仓库的 README 前 120 行。只按你看到的判断，不要推测作者。 -->

# PreJudge

**Judge your hackathon project with the organizer's own rubric — before the real judges do.**

PreJudge is a small agent built on the [OpenMinion](https://github.com/OpenMinion/openminion) 0.1 Python SDK.
Give it a hackathon's rules (a markdown file, or the DoraHacks page text pasted into a file) and your project
folder. It reads your repo with workspace-confined tools, scores every rubric criterion with **machine-verified
evidence**, lets a **skeptic subagent** challenge generous scores, and writes a report with concrete fixes.
Optionally a fixer agent drafts missing submission docs — **only after you approve each file**.

Built for Cortensor Hackathon #5. The rules for it ship with the tool:

```bash
prejudge cortensor-hackathon-5 path/to/your-project
```

> 🇩🇪 Deutsch: siehe [Kurzanleitung auf Deutsch](#kurzanleitung-auf-deutsch). Reports gibt es auf Englisch und Deutsch (`--lang de`).

## Why

Every hackathon page has a checklist and weighted criteria, and most submissions still lose points on things
that were knowable up front: no demo link, no setup steps, a findings note that was never written, a key
committed by accident. PreJudge turns the organizer's rubric into a repeatable pre-submission check you can
run after every change (and in CI with `--fail-under`).

## What one run does

```
rules.md ──► parse rubric + checklist (deterministic, weights from the organizer)
                │
project/ ──►  [1] Judge agent ── scan + file list + key files inlined; tools for drill-down:
                │      repo_tree, read_file, search_repo, submission_scan
                │      output_type=Scorecard (Pydantic), one durable session per project
                │      loop abort → tool-free fallback judge from the inlined files
                ▼
              Evidence gate ── every quote is checked against the file; a score > 5 without
                │               a verifiable quote is capped at 5
                ▼
              [2] Skeptic subagent (subagent(), bounded timeout, output_type=SkepticReview)
                │      sees scorecard + scan, challenges scores; PreJudge meets it halfway
                ▼
              [3] optional Fixer agent ── create_doc tool (write scope → approval_callback asks you)
                ▼
          weighted score (computed in Python) · history delta · PREJUDGE_REPORT.md · prejudge_report.html
```

The model never computes the final number: weights come from the rules file and the total is calculated
in code, so the score is reproducible and cannot be talked up.

## Setup

Requires Python 3.11+.

```bash
git clone https://github.com/ElTanque81/prejudge.git
cd prejudge
python3.11 -m venv .venv && source .venv/bin/activate
pip install -e '.[test]'

# configure a real model once (OpenMinion setup wizard)
openminion setup --no-chat          # choose e.g. cortensor-portal, groq, openai, ollama
openminion doctor --check-turn      # one real test turn
```

Using **Ollama** (local): OpenMinion does not pass a context size to Ollama, and Ollama's default window
(4096 tokens) is too small for agent turns. Raise it before running PreJudge, otherwise prompts are cut
off silently:

```bash
# macOS app: set it, then quit Ollama from the menu bar and open it again
launchctl setenv OLLAMA_CONTEXT_LENGTH 12288
# or when running the server yourself
OLLAMA_CONTEXT_LENGTH=12288 ollama serve
```

Tested with `qwen2.5:14b` on a 16 GB Mac mini.

Using **Otari** (Mozilla.ai's OpenAI-compatible gateway; the demo run used it): choose
`6` → `14` *Custom OpenAI-compatible endpoint*, base URL `https://api.otari.ai/api/v1`
(EU keys: `https://eu.api.otari.ai/api/v1`), model e.g. `alibaba/qwen3-235b-a22b-instruct-2507`,
and your Otari API key. If the test answers `HTTP 421`, your key belongs to the other region.

Using **Cortensor Portal**: pick `cortensor-portal` in the wizard (credential `CORTENSOR_API_KEY`,
endpoint `https://api.cortensor.app/v1`, recommended model `oss-20b`). Portal is slower than most hosted
providers, so pass `--timeout 900`.

## Run

```bash
# judge the bundled sample project against Cortensor Hackathon #5
prejudge cortensor-hackathon-5 examples/sample-project --config ~/.openminion/agents.json

# German report, let the fixer draft missing docs (asks before every file)
prejudge cortensor-hackathon-5 . --lang de --fix

# any hackathon: save the rules page text to a file and point PreJudge at it
prejudge my-hackathon-rules.txt ~/code/my-project

# CI gate: exit code 3 when the weighted score is below 70
prejudge cortensor-hackathon-5 . --fail-under 70
```

Output goes to `PROJECT/.prejudge/` (`PREJUDGE_REPORT.md`, `prejudge_report.html`, `history.json`).
Run it again after fixing things and the report shows the delta against the previous run.

| Option | Meaning |
|---|---|
| `--lang en\|de` | report language (or `PREJUDGE_LANG`) |
| `--config`, `--agent` | OpenMinion `agents.json` and agent profile |
| `--no-skeptic` | skip the skeptic subagent (faster, fewer calls) |
| `--fix` / `--yes` | fixer agent; `--yes` auto-approves file creation |
| `--timeout` | seconds per agent turn (default 600) |
| `--fail-under N` | exit 3 below N/100 |

### Rules file format

PreJudge needs weighted lines such as `Working functionality and useful outcome: 25%` and, ideally, a
checklist after a line like `Your PR should include:` (markdown bullets or plain lines pasted from the
web page both work). See `prejudge/rules_library/cortensor-hackathon-5.md`.
