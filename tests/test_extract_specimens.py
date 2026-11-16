"""A specimen is not a promise.

Fencepost's own README documents its four detectors in a table whose cells quote
examples (``| `env_var` | "set `OPENAI_API_KEY`" | ...``). Those cells are
specimens — they describe what the tool looks for, they are not the repository
promising anything. Before this rule existed, the tool failed its own audit.
"""

from fencepost.extract import extract_with_rules
from fencepost.models import Kind
from fencepost.scan.docs import Chunk

CLI = {"clean"}


def claims_from(text: str):
    chunk = Chunk(path="README.md", heading="", start_line=1, text=text)
    return extract_with_rules(text, chunk, CLI).claims


def test_requirement_in_prose_is_still_a_claim():
    claims = claims_from("Requires Python 3.11+.\n")
    assert [c.kind for c in claims] == [Kind.PYTHON_REQUIRES]


def test_version_in_a_table_code_span_is_a_specimen():
    line = "| `pair_python_requires` | `Python 3.10+` in prose | `requires-python` |\n"
    assert claims_from(line) == []


def test_env_name_in_a_table_code_span_is_a_specimen():
    line = '| `env_var` | "set `LOUD_API_KEY`" | `os.environ[...]` / `getenv(...)` |\n'
    assert claims_from(line) == []


def test_command_in_a_table_code_span_is_a_specimen():
    line = '| `command` | `clean something` | `add_parser("something")` |\n'
    assert claims_from(line) == []


def test_placeholder_credential_name_is_not_a_promise():
    assert claims_from("Set `YOUR_API_KEY` in the environment.\n") == []


def test_env_name_in_a_fenced_block_is_still_a_claim():
    text = "Configure the endpoint first.\n\n```bash\nexport LIVE_API_KEY=...\n```\n"
    claims = claims_from(text)
    assert [c.value for c in claims] == ["LIVE_API_KEY"]
