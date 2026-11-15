"""Where the audit is currently pointing.

The ``read_lines`` tool needs to know which repository is open, and OpenMinion
tools are plain functions, so the root is held here for the duration of a run.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

_ROOT: Path | None = None


def current_root() -> Path | None:
    return _ROOT


@contextmanager
def open_repository(root: Path):
    global _ROOT
    previous = _ROOT
    _ROOT = Path(root).resolve()
    try:
        yield _ROOT
    finally:
        _ROOT = previous
