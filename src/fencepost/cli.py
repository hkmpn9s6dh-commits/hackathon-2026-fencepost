"""``fencepost`` command line."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .audit import AuditOptions, run_audit
from .models import Kind, Ledger, Severity
from .report import drifting, render_html, render_markdown

FAIL_ON = {"high": Severity.HIGH, "medium": Severity.MEDIUM, "low": Severity.LOW, "none": None}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fencepost",
        description="Audit the gap between what a repository promises and what it does.",
    )
    parser.add_argument("--version", action="version", version=f"fencepost {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    audit = sub.add_parser("audit", help="audit a repository")
    audit.add_argument("path", nargs="?", default=".", help="repository root (default: .)")
    audit.add_argument("--out", default="", help="output directory (default: <repo>/fencepost-out)")
    audit.add_argument("--no-model", action="store_true", help="rules only; no model calls at all")
    audit.add_argument("--model", default=None, help="override the OpenMinion model id")
    audit.add_argument("--timeout", type=float, default=180.0, help="per-turn timeout in seconds")
    audit.add_argument(
        "--counter-reader",
        action="store_true",
        help="add the delegated adversary pass (one more turn; slow on CPU models)",
    )
    audit.add_argument("--two-pass", action="store_true", help="also run a separate reviewer pass before the counter-reader")
    audit.add_argument("--with-tools", action="store_true", help="let the reviewer call read_lines (slower)")
    audit.add_argument("--chunks", type=int, default=3, help="how many document chunks to send to the model")
    audit.add_argument("--only", default="", help="comma separated: python_requires,dependency,command,env_var")
    audit.add_argument(
        "--ignore",
        default=[],
        action="append",
        help="KIND:VALUE to accept knowingly, e.g. env_var:OPENAI_API_KEY (repeatable)",
    )
    audit.add_argument("--fail-on", choices=sorted(FAIL_ON), default="high", help="exit 1 at or above this severity")
    audit.add_argument("--yes", action="store_true", help="write the report without asking")
    audit.add_argument("--title", default="", help="title shown on the report")
    audit.add_argument("--quiet", action="store_true", help="no progress lines")

    explain = sub.add_parser("explain", help="print one finding from a ledger")
    explain.add_argument("ledger", help="path to ledger.json")
    explain.add_argument("finding_id", help="finding id (prefix is enough)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "explain":
        return _explain(Path(args.ledger), args.finding_id)
    return _audit(args)


def _audit(args) -> int:
    root = Path(args.path).resolve()
    if not root.is_dir():
        print(f"fencepost: not a directory: {root}", file=sys.stderr)
        return 2

    kinds = set(Kind)
    if args.only.strip():
        wanted = {part.strip() for part in args.only.split(",") if part.strip()}
        kinds = {kind for kind in Kind if kind.value in wanted}
        if not kinds:
            print(f"fencepost: no known kind in --only {args.only!r}", file=sys.stderr)
            return 2

    quiet = args.quiet
    log = (lambda message: None) if quiet else (lambda message: print(message, flush=True))
    print(f"fencepost · {root.name}", flush=True)
    options = AuditOptions(
        root=root,
        use_model=not args.no_model,
        model=args.model,
        timeout_seconds=args.timeout,
        reviewer_tools=args.with_tools,
        two_pass=args.two_pass,
        counter_reader=args.counter_reader,
        prospect_chunks=args.chunks,
        kinds=kinds,
        ignore={part.strip() for part in ",".join(args.ignore or []).split(",") if part.strip()},
        log=log,
    )
    ledger = run_audit(options)

    out_dir = Path(args.out) if args.out else root / "fencepost-out"
    title = args.title or root.name
    found = drifting(ledger)
    print("")
    print(f"  {len(found)} drift  ·  high {ledger.count(Severity.HIGH)}  ·  "
          f"refused quotes {ledger.run.claims_dropped}  ·  {ledger.run.duration_seconds}s")
    for index, finding in enumerate(found[:12], start=1):
        print(f"  {index:>2}. [{finding.severity.value:<6}] {finding.claim.file}:{finding.claim.line}  {finding.claim.quote[:88]}")
    if len(found) > 12:
        print(f"  … {len(found) - 12} more in the ledger")

    if not _approved(args, out_dir):
        print("  report not written (declined)")
        return _exit_code(ledger, args.fail_on)

    _write(ledger, out_dir, title)
    print(f"  written: {out_dir / 'ledger.json'}")
    print(f"           {out_dir / 'report.md'}")
    print(f"           {out_dir / 'report.html'}")
    return _exit_code(ledger, args.fail_on)


def _approved(args, out_dir: Path) -> bool:
    if args.yes or not sys.stdin.isatty():
        return True
    try:
        answer = input(f"write the report to {out_dir}? [y/N] ")
    except EOFError:
        return False
    return answer.strip().lower() in {"y", "yes"}


def _write(ledger: Ledger, out_dir: Path, title: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "ledger.json").write_text(
        json.dumps(ledger.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (out_dir / "report.md").write_text(render_markdown(ledger, title), encoding="utf-8")
    (out_dir / "report.html").write_text(render_html(ledger, title), encoding="utf-8")


def _exit_code(ledger: Ledger, fail_on: str) -> int:
    threshold = FAIL_ON[fail_on]
    if threshold is None:
        return 0
    rank = {Severity.HIGH: 3, Severity.MEDIUM: 2, Severity.LOW: 1}
    worst = max((rank[f.severity] for f in drifting(ledger)), default=0)
    return 1 if worst >= rank[threshold] else 0


def _explain(path: Path, needle: str) -> int:
    if not path.is_file():
        print(f"fencepost: no such ledger: {path}", file=sys.stderr)
        return 2
    ledger = Ledger.model_validate_json(path.read_text(encoding="utf-8"))
    matches = [f for f in ledger.findings if f.id.startswith(needle)]
    if not matches:
        print(f"fencepost: no finding starts with {needle!r}", file=sys.stderr)
        return 2
    finding = matches[0]
    print(f"{finding.id}  [{finding.severity.value}] {finding.kind.value}")
    print(f"  promise  {finding.claim.file}:{finding.claim.line}")
    print(f"           {finding.claim.quote}")
    if finding.implementation:
        print(f"  actual   {finding.implementation.file}:{finding.implementation.line}")
        print(f"           {finding.implementation.snippet or finding.implementation.value}")
    else:
        print("  actual   (nothing found)")
    print(f"  verdict  {finding.verdict.value} by {finding.adjudicated_by}")
    print(f"  why      {finding.why or finding.machine_reason}")
    if finding.rebutted:
        print(f"  rebuttal {finding.rebuttal}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
