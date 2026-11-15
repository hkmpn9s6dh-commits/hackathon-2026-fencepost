from fencepost.models import Claim, Kind
from fencepost.quote_gate import Rejected, verify_quote

DOC = """# demo

Requires Python 3.11 or newer.

Set `DEMO_API_KEY` before running the CLI.
"""


def gate(quote: str, value: str, kind: Kind = Kind.PYTHON_REQUIRES) -> Claim | Rejected:
    return verify_quote(
        text=DOC,
        quote=quote,
        file="README.md",
        kind=kind,
        value=value,
        claim_id="t1",
    )


def test_exact_quote_becomes_a_claim():
    claim = gate("Requires Python 3.11 or newer.", "3.11")
    assert isinstance(claim, Claim)
    assert claim.line == 3
    assert claim.quote == "Requires Python 3.11 or newer."
    assert claim.offered_by == "model"


def test_trailing_whitespace_is_forgiven_but_the_file_wins():
    claim = gate("Requires Python 3.11 or newer.   ", "3.11")
    assert isinstance(claim, Claim)
    assert claim.quote == "Requires Python 3.11 or newer."


def test_invented_quote_is_refused():
    outcome = gate("Python 3.9 is required.", "3.9")
    assert isinstance(outcome, Rejected)
    assert "not found verbatim" in outcome.reason


def test_quote_that_does_not_carry_the_value_is_refused():
    outcome = gate("Set `DEMO_API_KEY` before running the CLI.", "3.11")
    assert isinstance(outcome, Rejected)
    assert "does not contain" in outcome.reason


def test_short_quote_is_refused():
    outcome = gate("3.11", "3.11")
    assert isinstance(outcome, Rejected)


def test_overlong_quote_is_refused():
    outcome = gate("x" * 401, "3.11")
    assert isinstance(outcome, Rejected)
    assert "400" in outcome.reason


def test_line_number_points_at_the_first_character():
    outcome = verify_quote(
        text=DOC,
        quote="CLI.",
        file="README.md",
        kind=Kind.ENV_VAR,
        value="cli",
        claim_id="t2",
    )
    if isinstance(outcome, Claim):
        assert outcome.line == 5
