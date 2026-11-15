"""Rule-based claim extraction.

This is the cheap first pass. It runs with no model at all, which is what makes
``fencepost audit --no-model`` a real (if narrower) audit rather than a stub, and
what lets the test suite cover the pipeline hermetically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Claim, Kind
from .scan.docs import Chunk

PY_MENTION = re.compile(r"(?:requires?\s+)?Python\s*(?:>=|≥|>)?\s*3\.(\d+)", re.IGNORECASE)
ENV_MENTION = re.compile(r"\b([A-Z][A-Z0-9]{2,}_(?:API_KEY|ACCESS_KEY|TOKEN|SECRET|KEY|DSN))\b")
CREDENTIAL_HINT = re.compile(
    r"(api[ _-]?key|token|secret|credential|password|env(?:ironment)? var)", re.IGNORECASE
)
COMMAND_HINT = re.compile(r"`([a-z][a-z0-9_.-]{1,24})\s+([a-z][a-z0-9-]{1,24})")
INSTALL_HINT = re.compile(r"(pip install|uv add|pipx install|python -m pip)", re.IGNORECASE)


@dataclass(slots=True)
class Extraction:
    claims: list[Claim]
    dropped: list[dict]


def _line_of(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def _claim(chunk: Chunk, doc_text: str, needle: str, kind: Kind, value: str, ordinal: int) -> Claim | None:
    """Locate ``needle`` inside the whole document so the line number is real."""

    index = doc_text.find(needle)
    if index < 0:
        return None
    return Claim(
        id=f"{chunk.path}:{_line_of(doc_text, index)}:{kind.value}:{ordinal}",
        kind=kind,
        quote=needle,
        value=value,
        file=chunk.path,
        line=_line_of(doc_text, index),
        offered_by="rule",
    )


def extract_with_rules(doc_text: str, chunk: Chunk, cli_names: set[str]) -> Extraction:
    claims: list[Claim] = []
    dropped: list[dict] = []
    order = 0

    for match in PY_MENTION.finditer(chunk.text):
        line = _line_with(chunk.text, match.start())
        claim = _claim(chunk, doc_text, line, Kind.PYTHON_REQUIRES, f"3.{match.group(1)}", order)
        if claim and _fresh(claims, claim):
            claims.append(claim)
            order += 1

    if CREDENTIAL_HINT.search(chunk.text) or "```" in chunk.text:
        for match in ENV_MENTION.finditer(chunk.text):
            line = _line_with(chunk.text, match.start())
            claim = _claim(chunk, doc_text, line, Kind.ENV_VAR, match.group(1), order)
            if claim and _fresh(claims, claim):
                claims.append(claim)
                order += 1

    for match in COMMAND_HINT.finditer(chunk.text):
        binary, subcommand = match.group(1), match.group(2)
        if binary not in cli_names:
            continue
        tool_line = f"{binary} {subcommand}"
        claim = _claim(chunk, doc_text, tool_line, Kind.COMMAND, subcommand, order)
        if claim and _fresh(claims, claim):
            claims.append(claim)
            order += 1

    return Extraction(claims=claims, dropped=dropped)


def _line_with(text: str, index: int) -> str:
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    if end < 0:
        end = len(text)
    return text[start:end].strip()


def _fresh(claims: list[Claim], candidate: Claim) -> bool:
    return not any(c.kind is candidate.kind and c.value == candidate.value for c in claims)


def cli_names_for(project_name: str) -> set[str]:
    base = project_name.strip().lower()
    names = {base, base.replace("_", "-"), base.replace("-", "_")}
    names.discard("")
    return names


def prospect_score(chunk: Chunk) -> int:
    """How likely is this chunk to contain a promise worth a model call?"""

    score = 0
    if INSTALL_HINT.search(chunk.text):
        score += 3
    if PY_MENTION.search(chunk.text):
        score += 3
    if CREDENTIAL_HINT.search(chunk.text):
        score += 3
    if COMMAND_HINT.search(chunk.text):
        score += 2
    if "```" in chunk.text:
        score += 1
    return score
