"""Read what the project *declares* about itself."""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_DEP_LINE = re.compile(r"^\s*[\"']?([A-Za-z0-9_.\-]+)")


@dataclass(slots=True)
class Dependency:
    name: str
    line: int
    raw: str


@dataclass(slots=True)
class ProjectInfo:
    root: Path
    name: str
    requires_python: str | None = None
    requires_python_line: int = 0
    dependencies: list[Dependency] = field(default_factory=list)
    packages: list[str] = field(default_factory=list)
    has_pyproject: bool = False


def _find_key_line(text: str, key: str) -> int:
    pattern = re.compile(rf"^\s*{re.escape(key)}\s*=", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return 1
    return text.count("\n", 0, match.start()) + 1


def normalise_dist(name: str) -> str:
    """PEP 503 normalisation: ``Foo_Bar.baz`` and ``foo-bar-baz`` are one name."""

    return re.sub(r"[-_.]+", "-", name).lower()


def load_project(root: Path) -> ProjectInfo:
    path = root / "pyproject.toml"
    if not path.is_file():
        return ProjectInfo(root=root, name=root.name, has_pyproject=False)

    text = path.read_text(encoding="utf-8", errors="replace")
    data = tomllib.loads(text)
    project = data.get("project", {}) or {}

    name = str(project.get("name") or root.name)
    requires = project.get("requires-python")
    deps = [_dependency(entry, text) for entry in project.get("dependencies", []) or []]

    packages = _own_packages(root, data)

    return ProjectInfo(
        root=root,
        name=name,
        requires_python=str(requires) if requires else None,
        requires_python_line=_find_key_line(text, "requires-python") if requires else 0,
        dependencies=deps,
        packages=packages,
        has_pyproject=True,
    )


def _dependency(raw: str, pyproject_text: str) -> Dependency:
    name_match = _DEP_LINE.match(raw)
    name = name_match.group(1) if name_match else raw
    return Dependency(name=name, line=_find_key_line(pyproject_text, raw.strip()[:24]) if raw else 0, raw=raw)


def _own_packages(root: Path, data: dict) -> list[str]:
    found: set[str] = set()
    project = data.get("project", {}) or {}
    if project.get("name"):
        found.add(normalise_dist(str(project["name"])).replace("-", "_"))
    for base in (root / "src", root):
        if not base.is_dir():
            continue
        for child in base.iterdir():
            if child.is_dir() and (child / "__init__.py").is_file():
                found.add(child.name)
    return sorted(found)


def version_floor(marker: str | None) -> tuple[int, int] | None:
    """``">=3.11"`` -> ``(3, 11)``; ``">3.9,<4"`` -> ``(3, 10)``."""

    if not marker:
        return None
    best: tuple[int, int] | None = None
    for op, major, minor in re.findall(r"(>=|>|~=|\^)?\s*(\d+)\.(\d+)", marker):
        floor = (int(major), int(minor))
        if op == ">":
            floor = (floor[0], floor[1] + 1)
        if op == "~=":
            floor = (floor[0], floor[1])
        best = floor if best is None or floor > best else best
    if best is None:
        short = re.fullmatch(r"\s*(\d+)\s*", marker)
        if short:
            best = (int(short.group(1)), 0)
    return best
