"""Orchestration: rules first, then the model, then the counter-reader."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from collections.abc import Callable
from pathlib import Path

from . import detectors
from .bridge import Bridge
from .detectors import Repo, load_repo
from .extract import cli_names_for, extract_with_rules, prospect_score
from .models import (
    Candidate,
    Finding,
    Kind,
    Ledger,
    RunInfo,
    Severity,
    Verdict,
)
from .scan.docs import chunks
from .workspace import open_repository

DEFAULT_PROSPECT_CHUNKS = 3
MAX_MODEL_CLAIMS = 24


@dataclass
class AuditOptions:
    root: Path
    use_model: bool = True
    model: str | None = None
    timeout_seconds: float = 600.0
    prospect_chunks: int = DEFAULT_PROSPECT_CHUNKS
    kinds: set[Kind] = field(default_factory=lambda: set(Kind))
    reviewer_tools: bool = False
    two_pass: bool = False
    log: Callable[[str], None] | None = None


def run_audit(options: AuditOptions) -> Ledger:
    log = options.log or (lambda message: None)
    started = time.time()
    started_iso = _now()

    root = options.root.resolve()
    repo = load_repo(root)
    session_id = f"fencepost-{repo.project.name}"

    claims, dropped, bridge = _collect_claims(repo, options, log)
    log(f"  {len(claims)} promises survived the quote gate, {len(dropped)} refused")

    candidates = _pair(repo, claims, options.kinds)
    log(f"  {len(candidates)} pairs to judge")

    assessments = {}
    rebuttals = {}
    if options.use_model and bridge is not None:
        drifting = [c for c in candidates if c.machine_drift]
        if options.two_pass:
            log(f"  asking the reviewer about {min(len(drifting), 12)} of them")
            assessments = bridge.review(drifting, with_tools=options.reviewer_tools)
            drifting = [
                c for c in drifting
                if c.id not in assessments or assessments[c.id].verdict is Verdict.DRIFT
            ]
        if drifting:
            log(f"  counter-reader on {min(len(drifting), 10)} findings")
            rebuttals = bridge.rebut(drifting[:10])

    findings = _assemble(candidates, assessments, rebuttals, use_model=options.use_model)

    finished_iso = _now()
    metrics = bridge.metrics if bridge else None
    run = RunInfo(
        target=str(root.name),
        session_id=session_id,
        run_id=(metrics.run_ids[-1] if metrics and metrics.run_ids else None),
        model=options.model if options.use_model else None,
        provider="openminion" if options.use_model else "rules-only",
        mode="model" if options.use_model else "rule-only",
        started_at=started_iso,
        finished_at=finished_iso,
        duration_seconds=round(time.time() - started, 1),
        files_scanned=repo.files_scanned,
        claims_offered=len(claims) + len(dropped),
        claims_dropped=len(dropped),
        model_calls=metrics.calls if metrics else 0,
        model_failures=metrics.failures if metrics else 0,
        input_tokens=metrics.input_tokens if metrics else 0,
        output_tokens=metrics.output_tokens if metrics else 0,
        tool_calls=metrics.tool_calls if metrics else 0,
    )
    return Ledger(run=run, findings=findings, dropped_quotes=dropped)


def _collect_claims(repo: Repo, options: AuditOptions, log) -> tuple[list, list[dict], Bridge | None]:
    names = cli_names_for(repo.project.name)
    claims: list = []
    dropped: list[dict] = []

    scored: list[tuple[int, object, object]] = []
    for doc in repo.docs:
        for chunk in chunks(doc):
            rule_result = extract_with_rules(doc.text, chunk, names)
            _merge(claims, rule_result.claims)
            scored.append((prospect_score(chunk), doc, chunk))

    bridge: Bridge | None = None
    if not options.use_model:
        return claims, dropped, bridge

    bridge = Bridge(
        session_id=f"fencepost-{repo.project.name}",
        model=options.model,
        timeout_seconds=options.timeout_seconds,
        log=log,
    )
    scored.sort(key=lambda item: item[0], reverse=True)
    chosen_doc = None
    for score, doc, _chunk in scored:
        if score > 0:
            chosen_doc = doc
            break
    if chosen_doc is None:
        log("  nothing in the docs looked like a promise; skipping the model")
        return claims, dropped, bridge

    picked = [chunk for score, doc, chunk in scored if doc.path == chosen_doc.path and score > 0][
        : options.prospect_chunks
    ]
    budget = 2400
    trimmed: list = []
    used = 0
    for chunk in picked:
        if used + len(chunk.text) > budget and trimmed:
            break
        trimmed.append(chunk)
        used += len(chunk.text)
    log(f"  {len(scored)} document chunks, sending {len(trimmed)} from {chosen_doc.path} ({used} chars)")

    with open_repository(repo.root):
        offered, refused = bridge.propose(chosen_doc.text, trimmed)
    dropped.extend(refused)
    _merge(claims, offered, limit=MAX_MODEL_CLAIMS)

    return claims, dropped, bridge


def _merge(claims: list, incoming, limit: int | None = None) -> None:
    for claim in incoming:
        if limit is not None and len(claims) >= limit:
            return
        if any(existing.kind is claim.kind and existing.value == claim.value for existing in claims):
            continue
        if any(existing.quote == claim.quote and existing.file == claim.file for existing in claims):
            continue
        claims.append(claim)


def _pair(repo: Repo, claims: list, kinds: set[Kind]) -> list[Candidate]:
    out: list[Candidate] = []
    if Kind.PYTHON_REQUIRES in kinds:
        out += detectors.pair_python_requires(repo, [c for c in claims if c.kind is Kind.PYTHON_REQUIRES])
    if Kind.DEPENDENCY in kinds:
        out += detectors.pair_dependencies(repo, [])
    if Kind.COMMAND in kinds:
        out += detectors.pair_commands(repo, [c for c in claims if c.kind is Kind.COMMAND])
    if Kind.ENV_VAR in kinds:
        out += detectors.pair_env(repo, [c for c in claims if c.kind is Kind.ENV_VAR])
    return out


def _assemble(candidates, assessments, rebuttals, *, use_model: bool) -> list[Finding]:
    findings: list[Finding] = []
    for candidate in candidates:
        assessment = assessments.get(candidate.id)
        if assessment is not None:
            verdict, severity, why, by = (
                assessment.verdict,
                assessment.severity,
                assessment.why,
                "model",
            )
        else:
            verdict = Verdict.DRIFT if candidate.machine_drift else Verdict.CONSISTENT
            severity, why, by = candidate.machine_severity, candidate.machine_reason, "rule"
            if not use_model and candidate.machine_drift:
                by = "rule"

        rebuttal = rebuttals.get(candidate.id)
        findings.append(
            Finding(
                id=candidate.id,
                kind=candidate.kind,
                verdict=verdict,
                severity=severity,
                claim=candidate.claim,
                implementation=candidate.implementation,
                machine_reason=candidate.machine_reason,
                why=why,
                rebutted=bool(rebuttal and rebuttal.rebut),
                rebuttal=(rebuttal.reason if rebuttal else ""),
                adjudicated_by=by,
            )
        )
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    findings.sort(key=lambda f: (order[f.severity], f.kind.value, f.id))
    return findings


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
