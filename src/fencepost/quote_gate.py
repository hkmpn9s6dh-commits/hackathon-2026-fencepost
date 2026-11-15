"""The quote gate.

Everything else in Fencepost is negotiable; this module is not. A language
model may *propose* that a document promises something, but the proposal only
becomes a :class:`~fencepost.models.Claim` if the exact string it quotes can be
found in the file it says it came from.

The gate returns the file's own bytes as the stored quote, never the model's
copy, so a claim can never drift away from its evidence.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Claim, Kind

MAX_QUOTE_CHARS = 400
MIN_QUOTE_CHARS = 8


@dataclass(slots=True)
class Rejected:
    """A quote the gate refused, kept so the report can count the refusals."""

    quote: str
    reason: str
    file: str


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _line_normalised(text: str) -> tuple[str, list[int]]:
    """Strip trailing whitespace per line, remembering where each line started."""

    starts: list[int] = []
    out: list[str] = []
    cursor = 0
    for raw in text.split("\n"):
        starts.append(cursor)
        out.append(raw.rstrip())
        cursor += len(raw) + 1
    return "\n".join(out), starts


def verify_quote(
    *,
    text: str,
    quote: str,
    file: str,
    kind: Kind,
    value: str,
    claim_id: str,
) -> Claim | Rejected:
    """Turn a proposed quote into a Claim, or explain why it cannot be one."""

    proposed = (quote or "").strip()
    if len(proposed) < MIN_QUOTE_CHARS:
        return Rejected(quote=proposed, reason="quote too short to be evidence", file=file)
    if len(proposed) > MAX_QUOTE_CHARS:
        return Rejected(quote=proposed[:120], reason="quote longer than 400 characters", file=file)

    index = text.find(proposed)
    stored = proposed
    line = _line_of(text, index) if index >= 0 else 1

    if index < 0:
        # Second chance: the model often adds or drops trailing spaces.
        flat_text, starts = _line_normalised(text)
        flat_quote, _ = _line_normalised(proposed)
        flat_index = flat_text.find(flat_quote)
        if flat_index < 0:
            return Rejected(
                quote=proposed[:120],
                reason="not found verbatim in the file",
                file=file,
            )
        line = _line_index_to_line(starts, flat_index)
        stored = _slice_original(text, flat_quote, flat_index, starts)

    if not _value_supported(value, stored):
        return Rejected(
            quote=proposed[:120],
            reason=f"quote does not contain the claimed value {value!r}",
            file=file,
        )

    return Claim(
        id=claim_id,
        kind=kind,
        quote=stored,
        value=value,
        file=file,
        line=line,
        offered_by="model",
    )


def _line_index_to_line(starts: list[int], flat_index: int) -> int:
    line = 1
    for number, start in enumerate(starts, start=1):
        if start <= flat_index:
            line = number
        else:
            break
    return line


def _slice_original(text: str, flat_quote: str, flat_index: int, starts: list[int]) -> str:
    """Map a normalised match back onto the original file text."""

    first_line = _line_index_to_line(starts, flat_index) - 1
    span = flat_quote.count("\n") + 1
    lines = text.split("\n")
    return "\n".join(lines[first_line : first_line + span])


def _value_supported(value: str, quote: str) -> bool:
    needle = value.strip()
    if not needle:
        return False
    haystack = quote.lower()
    if needle.lower() in haystack:
        return True
    # A version floor is allowed to appear as "3.11" inside "3.11+".
    compact = re.sub(r"[\s_\-]", "", haystack)
    return re.sub(r"[\s_\-]", "", needle.lower()) in compact
