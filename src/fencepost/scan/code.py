"""Read what the project *actually does*, without importing it.

Everything here is static: Fencepost never imports the target project, so an
audit cannot run someone's ``setup.py`` or trip a module-level side effect.
"""

from __future__ import annotations

import ast
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

IGNORED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "env",
    "__pycache__",
    "node_modules",
    "build",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    "site-packages",
    ".eggs",
}

STDLIB = set(sys.stdlib_module_names) | {"__future__"}


@dataclass(slots=True)
class CodeRef:
    value: str
    file: str
    line: int
    snippet: str = ""


def python_files(root: Path, excludes: tuple[str, ...] = ()) -> Iterator[Path]:
    for path in sorted(root.rglob("*.py")):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        rel = _rel(path, root)
        if any(rel == item or rel.startswith(item.rstrip("/") + "/") for item in excludes):
            continue
        yield path


def _rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _parse(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return None


def count_python_files(root: Path, excludes: tuple[str, ...] = ()) -> int:
    return sum(1 for _ in python_files(root, excludes))


def collect_imports(root: Path, excludes: tuple[str, ...] = ()) -> dict[str, CodeRef]:
    """Top-level module names imported anywhere in the tree."""

    found: dict[str, CodeRef] = {}
    for path in python_files(root, excludes):
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    _record(found, alias.name.split(".")[0], rel, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                if node.level:
                    continue
                if not node.module:
                    continue
                _record(found, node.module.split(".")[0], rel, node.lineno)
    return found


def _record(found: dict[str, CodeRef], name: str, rel: str, line: int) -> None:
    if not name or name in STDLIB:
        return
    found.setdefault(name, CodeRef(value=name, file=rel, line=line))


ENV_NAMES = (
    "environ",
    "getenv",
)


def collect_env_reads(root: Path, excludes: tuple[str, ...] = ()) -> dict[str, CodeRef]:
    """Environment variables the code actually reads."""

    found: dict[str, CodeRef] = {}
    for path in python_files(root, excludes):
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        for node in ast.walk(tree):
            name = _env_name(node)
            if name:
                found.setdefault(name, CodeRef(value=name, file=rel, line=node.lineno))
    return found


def _env_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Subscript):
        if _is_environ(node.value):
            key = node.slice
            if isinstance(key, ast.Constant) and isinstance(key.value, str):
                return key.value
        return None
    if isinstance(node, ast.Call):
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in ENV_NAMES:
            if func.attr == "getenv" or _is_environ(func.value):
                if node.args and isinstance(node.args[0], ast.Constant):
                    value = node.args[0].value
                    if isinstance(value, str):
                        return value
        if isinstance(func, ast.Name) and func.id == "getenv":
            if node.args and isinstance(node.args[0], ast.Constant):
                value = node.args[0].value
                if isinstance(value, str):
                    return value
    return None


def _is_environ(node: ast.AST) -> bool:
    if isinstance(node, ast.Attribute) and node.attr == "environ":
        return True
    return isinstance(node, ast.Name) and node.id == "environ"


def collect_subcommands(root: Path, excludes: tuple[str, ...] = ()) -> dict[str, CodeRef]:
    """``subparsers.add_parser("doctor")`` — the real command surface."""

    found: dict[str, CodeRef] = {}
    for path in python_files(root, excludes):
        tree = _parse(path)
        if tree is None:
            continue
        rel = _rel(path, root)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not isinstance(func, ast.Attribute) or func.attr != "add_parser":
                continue
            if not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                found.setdefault(
                    first.value,
                    CodeRef(value=first.value, file=rel, line=node.lineno),
                )
    return found
