"""Typed records Fencepost passes between stages.

The important invariant lives here: a :class:`Claim` may only be constructed
through :func:`fencepost.quote_gate.verify_quote`, which is what makes it
impossible for the language model to contribute evidence that is not literally
present in the repository.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import BaseModel, Field


class Kind(str, Enum):
    """The four kinds of promise Fencepost knows how to check."""

    PYTHON_REQUIRES = "python_requires"
    DEPENDENCY = "dependency"
    COMMAND = "command"
    ENV_VAR = "env_var"


class Severity(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Verdict(str, Enum):
    DRIFT = "drift"
    CONSISTENT = "consistent"
    UNCLEAR = "unclear"


class Claim(BaseModel):
    """A promise made by prose, anchored to a verbatim quote in a real file."""

    id: str
    kind: Kind
    quote: str = Field(description="Exact substring of the source file, newlines included.")
    value: str = Field(description="Normalised subject: version floor, package, command or env var.")
    file: str = Field(description="Repository-relative path.")
    line: int = Field(ge=1, description="1-based line number of the first character of the quote.")
    offered_by: Literal["model", "rule"] = "rule"


class Implementation(BaseModel):
    """A fact about what the repository actually does, read from code or config."""

    kind: Kind
    value: str
    file: str
    line: int = Field(ge=1)
    snippet: str = ""
    detail: str = ""


class Candidate(BaseModel):
    """A claim paired with the implementation that should back it up."""

    id: str
    kind: Kind
    claim: Claim
    implementation: Implementation | None = None
    machine_reason: str = Field(
        default="",
        description="Why the deterministic layer paired (or failed to pair) these two records.",
    )
    machine_severity: Severity = Severity.MEDIUM
    machine_drift: bool = Field(
        default=True,
        description="False when the deterministic layer already found the two sides consistent.",
    )


class Rebuttal(BaseModel):
    """The counter-reader's answer: try to knock the finding down."""

    rebut: bool = Field(description="True when the finding does not survive scrutiny.")
    reason: str = Field(default="", description="At most 240 characters.")


class Assessment(BaseModel):
    """The adjudicator's structured answer for one candidate."""

    verdict: Verdict
    severity: Severity = Severity.MEDIUM
    why: str = Field(default="", description="At most 240 characters, must cite line numbers.")


class Finding(BaseModel):
    """A candidate that survived adjudication and rebuttal."""

    id: str
    kind: Kind
    verdict: Verdict
    severity: Severity
    claim: Claim
    implementation: Implementation | None = None
    machine_reason: str = ""
    why: str = ""
    rebutted: bool = False
    rebuttal: str = ""
    adjudicated_by: Literal["model", "rule", "none"] = "none"

    @property
    def is_drift(self) -> bool:
        return self.verdict is Verdict.DRIFT


class RunInfo(BaseModel):
    """Provenance for one audit. Every field is measured, not guessed."""

    target: str
    session_id: str
    run_id: str | None = None
    model: str | None = None
    provider: str | None = None
    mode: Literal["model", "rule-only"] = "rule-only"
    started_at: str
    finished_at: str
    duration_seconds: float
    files_scanned: int = 0
    claims_offered: int = 0
    claims_dropped: int = 0
    model_calls: int = 0
    model_failures: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    tool_calls: int = 0


class Ledger(BaseModel):
    """The evidence book. Machine-readable, diffable, and the only source of truth."""

    version: int = 1
    run: RunInfo
    findings: list[Finding] = Field(default_factory=list)
    rejected_rebuttals: list[dict] = Field(
        default_factory=list,
        description="Counter-reader claims that were refused for lack of evidence.",
    )
    dropped_quotes: list[dict] = Field(
        default_factory=list,
        description="Quotes the model offered that did not exist verbatim in the file.",
    )

    def count(self, severity: Severity | None = None) -> int:
        live = [f for f in self.findings if f.is_drift and not f.rebutted]
        if severity is None:
            return len(live)
        return sum(1 for f in live if f.severity is severity)

    def breakdown(self) -> dict[str, int]:
        out: dict[str, int] = {}
        for finding in self.findings:
            if not finding.is_drift:
                continue
            out[finding.kind.value] = out.get(finding.kind.value, 0) + 1
        return out
