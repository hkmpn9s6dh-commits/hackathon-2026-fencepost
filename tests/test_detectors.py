import pytest
from conftest import FIXTURES

from fencepost.audit import AuditOptions, run_audit
from fencepost.models import Kind, Severity
from fencepost.report import drifting, render_html, render_markdown


def audit(name: str):
    return run_audit(AuditOptions(root=FIXTURES / name, use_model=False))


def kinds(found):
    return sorted(f.kind.value for f in found)


def test_python_floor_mismatch_is_high(tmp_path):
    ledger = audit("python-floor")
    found = drifting(ledger)
    assert len(found) == 1
    assert found[0].kind is Kind.PYTHON_REQUIRES
    assert found[0].severity is Severity.HIGH
    assert found[0].claim.value == "3.10"
    assert found[0].implementation.value == ">=3.11"


def test_undeclared_import_is_high_and_unused_dep_is_low():
    ledger = audit("missing-dep")
    found = drifting(ledger)
    assert [f.kind.value for f in found] == ["dependency", "dependency"]
    by_id = {f.id: f for f in found}
    assert by_id["dep-undec-yaml"].severity is Severity.HIGH
    assert by_id["dep-unused-requests"].severity is Severity.LOW


def test_documented_command_that_does_not_exist_is_high():
    ledger = audit("phantom-command")
    found = drifting(ledger)
    assert len(found) == 1
    assert found[0].kind is Kind.COMMAND
    assert found[0].claim.value == "doctor"
    assert found[0].implementation is None


def test_credential_nobody_reads_is_high():
    ledger = audit("ghost-env")
    found = drifting(ledger)
    assert len(found) == 1
    assert found[0].kind is Kind.ENV_VAR
    assert found[0].claim.value == "GHOST_API_KEY"


def test_consistent_repository_reports_nothing():
    ledger = audit("clean")
    assert drifting(ledger) == []
    assert ledger.findings, "the ledger should still record what was checked"


def test_multi_fixture_finds_three_high_and_one_low():
    ledger = audit("multi")
    found = drifting(ledger)
    assert len([f for f in found if f.severity is Severity.HIGH]) == 3
    assert len([f for f in found if f.severity is Severity.LOW]) == 1
    assert sorted(set(kinds(found))) == ["command", "dependency", "python_requires"]


def test_every_finding_carries_a_real_quote():
    for name in ("python-floor", "missing-dep", "phantom-command", "ghost-env", "multi"):
        ledger = audit(name)
        for finding in drifting(ledger):
            text = (FIXTURES / name / finding.claim.file).read_text(encoding="utf-8")
            assert finding.claim.quote in text, finding.id
            assert finding.claim.line == text.count("\n", 0, text.find(finding.claim.quote)) + 1


def test_run_info_is_measured_not_guessed():
    ledger = audit("multi")
    assert ledger.run.mode == "rule-only"
    assert ledger.run.model is None
    assert ledger.run.model_calls == 0
    assert ledger.run.files_scanned > 0
    assert ledger.run.claims_offered >= 2


def test_markdown_and_html_render_the_same_findings():
    ledger = audit("multi")
    markdown = render_markdown(ledger, "multi")
    html = render_html(ledger, "multi")
    assert "漂移清单" in markdown
    assert "multi verify" in markdown
    assert "multi verify" in html
    assert "<script" not in html.lower()


def test_html_escapes_untrusted_quotes():
    from fencepost.models import Claim, Finding, Kind as K, Ledger, RunInfo, Severity as S, Verdict

    claim = Claim(
        id="x",
        kind=K.COMMAND,
        quote="<script>alert(1)</script>",
        value="doctor",
        file="README.md",
        line=1,
    )
    finding = Finding(
        id="x",
        kind=K.COMMAND,
        verdict=Verdict.DRIFT,
        severity=S.HIGH,
        claim=claim,
    )
    run = RunInfo(target="t", session_id="s", started_at="now", finished_at="now", duration_seconds=0.1)
    html = render_html(Ledger(run=run, findings=[finding]), "t")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_unknown_only_kind_is_rejected_by_cli():
    from fencepost.cli import main

    assert main(["audit", str(FIXTURES / "clean"), "--no-model", "--yes", "--only", "nonsense"]) == 2
