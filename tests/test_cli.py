import json

import pytest
from conftest import FIXTURES

from fencepost import audit as audit_module
from fencepost.cli import main


def test_exit_code_is_zero_on_a_clean_repository(tmp_path):
    assert main(["audit", str(FIXTURES / "clean"), "--no-model", "--yes", "--out", str(tmp_path)]) == 0


def test_exit_code_is_one_when_a_high_drift_exists(tmp_path):
    code = main(
        ["audit", str(FIXTURES / "phantom-command"), "--no-model", "--yes", "--out", str(tmp_path)]
    )
    assert code == 1


def test_fail_on_none_never_fails(tmp_path):
    code = main(
        [
            "audit",
            str(FIXTURES / "phantom-command"),
            "--no-model",
            "--yes",
            "--out",
            str(tmp_path),
            "--fail-on",
            "none",
        ]
    )
    assert code == 0


def test_report_files_are_written_and_the_ledger_is_valid_json(tmp_path):
    main(["audit", str(FIXTURES / "multi"), "--no-model", "--yes", "--out", str(tmp_path)])
    for name in ("ledger.json", "report.md", "report.html"):
        assert (tmp_path / name).is_file(), name
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert ledger["version"] == 1
    assert ledger["run"]["mode"] == "rule-only"
    assert ledger["findings"]


def test_only_filters_the_kinds(tmp_path):
    main(
        [
            "audit",
            str(FIXTURES / "multi"),
            "--no-model",
            "--yes",
            "--out",
            str(tmp_path),
            "--only",
            "command",
        ]
    )
    ledger = json.loads((tmp_path / "ledger.json").read_text(encoding="utf-8"))
    assert {finding["kind"] for finding in ledger["findings"]} == {"command"}


def test_missing_path_is_a_usage_error(tmp_path):
    assert main(["audit", str(tmp_path / "nope"), "--no-model", "--yes"]) == 2


def test_explain_prints_one_finding(tmp_path, capsys):
    main(["audit", str(FIXTURES / "multi"), "--no-model", "--yes", "--out", str(tmp_path)])
    code = main(["explain", str(tmp_path / "ledger.json"), "dep-undec-yaml"])
    out = capsys.readouterr().out
    assert code == 0
    assert "dep-undec-yaml" in out
    assert "promise" in out


def test_no_model_never_constructs_a_bridge(tmp_path, monkeypatch):
    def explode(*args, **kwargs):
        raise AssertionError("Bridge must not be constructed with --no-model")

    monkeypatch.setattr(audit_module, "Bridge", explode)
    assert main(["audit", str(FIXTURES / "clean"), "--no-model", "--yes", "--out", str(tmp_path)]) == 0
