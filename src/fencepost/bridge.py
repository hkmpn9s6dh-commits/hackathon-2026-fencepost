"""The OpenMinion side of Fencepost.

Three jobs are delegated to a real language model, and nothing else:

``propose``   read a chunk of prose and offer quotes that look like promises
``review``    look at each machine-found drift and say whether it survives context
``rebut``     a delegated counter-reader whose only job is to knock findings down

Every proposal goes through :mod:`fencepost.quote_gate` before it is allowed to
become evidence, so a hallucinated quote can only ever appear in the ledger as a
*refused* proposal, with the reason it was refused.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, Field

from openminion.api import Agent, AgentOutputValidationError, subagent
from openminion.tools import tool

from .models import Assessment, Candidate, Claim, Rebuttal, Severity, Verdict
from .scan.docs import Chunk

EXTRACT_INSTRUCTIONS = """You extract promises from project documentation.

You do not call tools. Reply with ONE JSON object and nothing else:
{"claims": [{"kind": "...", "quote": "...", "value": "..."}]}

Rules:
1. "quote" must be copied character for character from the DOCUMENT.
2. "kind" is python_requires, command or env_var.
3. "value" is the bare subject: "3.11", "doctor", "OPENAI_API_KEY".
4. Skip history, marketing and third-party tools.
5. Nothing to report: {"claims": []}"""

REVIEW_INSTRUCTIONS = """You review one machine-found inconsistency between a promise
and a codebase. You may call read_lines to see more surrounding code.

Reply with ONE JSON object and nothing else:
{"items": [{"id": "...", "drift": true, "severity": "high", "why": "..."}]}

"drift" is true only when a user following the document would be misled.
Set drift false when the document is talking about something else, when the
promise is historical, or when the snippet already satisfies it.
"why" must name the file and line, at most 200 characters.
severity is high, medium, or low."""

REBUT_INSTRUCTIONS = """You are the counter-reader. Your job is to knock findings down.

Reply with ONE JSON object and nothing else:
{"items": [{"id": "...", "rebut": true, "reason": "..."}]}

Say rebut=true when the finding is not actually a contradiction: the two sides
talk about different things, the promise is scoped to another tool, or the code
snippet already proves the promise. Otherwise rebut=false.
"reason" is at most 200 characters and must point at the text you relied on."""


class Proposal(BaseModel):
    kind: Literal["python_requires", "dependency", "command", "env_var"]
    quote: str
    value: str


class Proposals(BaseModel):
    claims: list[Proposal] = Field(default_factory=list)


class ReviewItem(BaseModel):
    id: str
    drift: bool
    severity: Literal["high", "medium", "low"] = "medium"
    why: str = ""


class Reviews(BaseModel):
    items: list[ReviewItem] = Field(default_factory=list)


class RebuttalItem(BaseModel):
    id: str
    rebut: bool
    reason: str = ""


class RebuttalBatch(BaseModel):
    items: list[RebuttalItem] = Field(default_factory=list)


@tool(min_scope="READ_ONLY", idempotent=True)
def read_lines(path: str, start: int = 1, count: int = 24) -> dict:
    """Read up to 60 lines of a file in the repository under audit."""

    from .workspace import current_root

    root = current_root()
    if root is None:
        return {"error": "no repository is open"}
    target = (root / path).resolve()
    try:
        target.relative_to(root.resolve())
    except ValueError:
        return {"error": "path escapes the repository"}
    if not target.is_file():
        return {"error": f"no such file: {path}"}
    lines = target.read_text(encoding="utf-8", errors="replace").split("\n")
    start = max(1, min(start, len(lines)))
    count = max(1, min(count, 60))
    window = lines[start - 1 : start - 1 + count]
    return {
        "path": path,
        "start": start,
        "lines": [f"{start + i}: {text}" for i, text in enumerate(window)],
    }


@dataclass
class BridgeMetrics:
    calls: int = 0
    failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0
    seconds: float = 0.0
    run_ids: list[str] = field(default_factory=list)


class Bridge:
    """A thin, measurable wrapper around the OpenMinion agents Fencepost uses."""

    def __init__(
        self,
        *,
        session_id: str,
        model: str | None = None,
        timeout_seconds: float = 600.0,
        log=None,
    ) -> None:
        self.session_id = session_id
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.metrics = BridgeMetrics()
        self._log = log or (lambda message: None)

    # ------------------------------------------------------------------ extract

    def propose(self, doc_text: str, chunks: list[Chunk]) -> tuple[list[Claim], list[dict]]:
        from .quote_gate import verify_quote

        chunks_text = "\n\n".join(
            f"<<<CHUNK {chunk.path}:{chunk.start_line}>>>\n{chunk.text}" for chunk in chunks
        )
        prompt = f"<DOCUMENT>\n{chunks_text}\n</DOCUMENT>"
        result = self._call(
            label=f"propose {len(chunks)} chunk(s)",
            instructions=EXTRACT_INSTRUCTIONS,
            output_type=Proposals,
            message=prompt,
        )
        if result is None:
            return [], []

        claims: list[Claim] = []
        dropped: list[dict] = []
        for index, proposal in enumerate(result.claims):
            outcome = verify_quote(
                text=doc_text,
                quote=proposal.quote,
                file=chunks[0].path,
                kind=proposal.kind,  # type: ignore[arg-type]
                value=proposal.value,
                claim_id=f"{chunks[0].path}:{index}:m",
            )
            if isinstance(outcome, Claim):
                claims.append(outcome)
            else:
                dropped.append({"quote": outcome.quote, "reason": outcome.reason, "file": outcome.file})
        return claims, dropped

    # ------------------------------------------------------------------- review

    def review(self, candidates: list[Candidate], *, with_tools: bool = False) -> dict[str, Assessment]:
        if not candidates:
            return {}

        payload = [
            {
                "id": item.id,
                "kind": item.kind.value,
                "promise": item.claim.quote,
                "promise_at": f"{item.claim.file}:{item.claim.line}",
                "machine_reason": item.machine_reason,
                "code_at": (
                    f"{item.implementation.file}:{item.implementation.line}"
                    if item.implementation
                    else "not found"
                ),
                "code": item.implementation.snippet if item.implementation else "",
            }
            for item in candidates[:12]
        ]
        message = (
            "Review these findings. Reply with one JSON object.\n"
            + json.dumps(payload, ensure_ascii=False, indent=1)[:6000]
        )
        result = self._call(
            label=f"review {len(payload)} findings",
            instructions=REVIEW_INSTRUCTIONS,
            output_type=Reviews,
            message=message,
            tools=[read_lines] if with_tools else [],
        )
        if result is None:
            return {}
        out: dict[str, Assessment] = {}
        for item in result.items:
            out[item.id] = Assessment(
                verdict=Verdict.DRIFT if item.drift else Verdict.CONSISTENT,
                severity=Severity(item.severity),
                why=item.why[:240],
            )
        return out

    # -------------------------------------------------------------------- rebut

    def rebut(self, candidates: list[Candidate]) -> dict[str, Rebuttal]:
        if not candidates:
            return {}
        payload = [
            {
                "id": item.id,
                "promise": item.claim.quote,
                "promise_at": f"{item.claim.file}:{item.claim.line}",
                "code": item.implementation.snippet if item.implementation else "(nothing found)",
                "code_at": (
                    f"{item.implementation.file}:{item.implementation.line}"
                    if item.implementation
                    else "not found"
                ),
                "reason": item.machine_reason,
            }
            for item in candidates[:10]
        ]
        parent = Agent(
            instructions=REVIEW_INSTRUCTIONS,
            output_type=Reviews,
            tools=[],
            name="fencepost-reviewer",
            session_id=self.session_id,
            model=self.model,
        )
        child = subagent(
            parent,
            instructions=REBUT_INSTRUCTIONS,
            output_type=RebuttalBatch,
            name="fencepost-counter-reader",
            timeout_seconds=int(self.timeout_seconds),
        )
        message = (
            "Try to knock these findings down. Reply with one JSON object.\n"
            + json.dumps(payload, ensure_ascii=False, indent=1)[:5000]
        )
        started = time.time()
        try:
            result = child.run(message, timeout_seconds=self.timeout_seconds)
        except Exception as exc:  # noqa: BLE001 - a refused rebuttal must not kill an audit
            self.metrics.failures += 1
            self._log(f"    rebut failed: {type(exc).__name__}: {str(exc)[:160]}")
            return {}
        finally:
            self.metrics.seconds += time.time() - started
        self.metrics.calls += 1
        self._record_stats(getattr(result, "stats", {}) or {}, getattr(result, "run_id", None))
        output = result.output
        if not isinstance(output, RebuttalBatch):
            return {}
        known = {entry["id"] for entry in payload}
        return {
            item.id: Rebuttal(rebut=item.rebut, reason=item.reason[:240])
            for item in output.items
            if item.id in known
        }

    # --------------------------------------------------------------------- call

    def _call(self, *, label, instructions, output_type, message, tools=None):
        agent = Agent(
            instructions=instructions,
            output_type=output_type,
            tools=tools if tools is not None else [],
            name="fencepost",
            session_id=self.session_id,
            model=self.model,
        )
        for attempt in (1, 2):
            started = time.time()
            try:
                result = agent.run(message, timeout_seconds=self.timeout_seconds)
            except AgentOutputValidationError as exc:
                self.metrics.failures += 1
                self._log(f"    {label}: invalid JSON (attempt {attempt}) {str(exc)[:120]}")
                message = message + "\n\nREMINDER: reply with ONE JSON object, no prose."
                continue
            except Exception as exc:  # noqa: BLE001
                self.metrics.failures += 1
                self._log(f"    {label}: {type(exc).__name__}: {str(exc)[:160]}")
                return None
            finally:
                self.metrics.seconds += time.time() - started
            self.metrics.calls += 1
            self._record_stats(result.stats or {}, result.run_id)
            self._log(f"    {label}: {result.run_state} {result.stats.get('llm_calls', '?')} llm calls")
            return result.output
        return None

    def _record_stats(self, stats: dict, run_id: str | None) -> None:
        self.metrics.input_tokens += int(stats.get("input_tokens") or 0)
        self.metrics.output_tokens += int(stats.get("output_tokens") or 0)
        self.metrics.tool_calls += int(stats.get("tool_calls") or 0)
        if run_id:
            self.metrics.run_ids.append(run_id)

