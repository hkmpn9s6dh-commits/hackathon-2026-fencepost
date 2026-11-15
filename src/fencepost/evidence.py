"""Build located evidence from the repository itself (no model involved)."""

from __future__ import annotations

from .models import Claim, Implementation, Kind


class EvidenceError(RuntimeError):
    """Raised when code asks for a quote that is not actually in the file."""


def rule_claim(
    *,
    text: str,
    quote: str,
    file: str,
    kind: Kind,
    value: str,
    claim_id: str,
) -> Claim:
    """A claim the tool can make on its own authority — still quote-anchored."""

    index = text.find(quote)
    if index < 0:
        raise EvidenceError(f"rule claim quote not found in {file}: {quote[:60]!r}")
    return Claim(
        id=claim_id,
        kind=kind,
        quote=quote,
        value=value,
        file=file,
        line=text.count("\n", 0, index) + 1,
        offered_by="rule",
    )


def implementation(
    *,
    kind: Kind,
    value: str,
    file: str,
    line: int,
    snippet: str = "",
    detail: str = "",
) -> Implementation:
    return Implementation(kind=kind, value=value, file=file, line=line, snippet=snippet, detail=detail)
