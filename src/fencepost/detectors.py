"""The four deterministic detectors.

Each detector pairs a located promise with a located fact. The pairing rules are
plain code you can read and test; no model touches them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from .evidence import implementation, rule_claim
from .models import Candidate, Claim, Kind, Severity
from .scan.code import (
    CodeRef,
    collect_env_reads,
    collect_imports,
    collect_subcommands,
    count_python_files,
    python_files,
)
from .scan.docs import DocFile, doc_files
from .scan.project import ProjectInfo, load_project, normalise_dist, version_floor

# Distribution name -> import name, only where they differ.
IMPORT_ALIASES = {
    "pyyaml": "yaml",
    "pillow": "pil",
    "python-dateutil": "dateutil",
    "beautifulsoup4": "bs4",
    "attrs": "attr",
    "ruamel-yaml": "ruamel",
    "protobuf": "google",
    "grpcio": "grpc",
    "opencv-python": "cv2",
    "scikit-learn": "sklearn",
    "pyjwt": "jwt",
    "python-multipart": "multipart",
    "charset-normalizer": "charset_normalizer",
    "importlib-metadata": "importlib_metadata",
    "typing-extensions": "typing_extensions",
    "pydantic-core": "pydantic_core",
    "setuptools": "pkg_resources",
    "python-dotenv": "dotenv",
    "msgpack-python": "msgpack",
    "psycopg2-binary": "psycopg2",
    "email-validator": "email_validator",
    "tomli-w": "tomli_w",
}

MAX_FINDINGS_PER_KIND = 12


@dataclass(slots=True)
class Repo:
    root: Path
    project: ProjectInfo
    imports: dict[str, CodeRef] = field(default_factory=dict)
    env_reads: dict[str, CodeRef] = field(default_factory=dict)
    subcommands: dict[str, CodeRef] = field(default_factory=dict)
    docs: list[DocFile] = field(default_factory=list)
    pyproject_text: str = ""
    files_scanned: int = 0
    local_modules: set[str] = field(default_factory=set)


IGNORE_FILE = ".fencepostignore"


def read_ignores(root: Path) -> tuple[str, ...]:
    path = root / IGNORE_FILE
    if not path.is_file():
        return ()
    entries = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        text = line.strip()
        if text and not text.startswith("#"):
            entries.append(text)
    return tuple(entries)


def load_repo(root: Path) -> Repo:
    project = load_project(root)
    excludes = read_ignores(root) + ("fencepost-out",)
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8", errors="replace") if pyproject.is_file() else ""
    repo = Repo(root=root, project=project, pyproject_text=text)
    repo.imports = collect_imports(root, excludes)
    repo.env_reads = collect_env_reads(root, excludes)
    repo.subcommands = collect_subcommands(root, excludes)
    repo.docs = doc_files(root)
    repo.files_scanned = count_python_files(root, excludes) + len(repo.docs) + (
        1 if project.has_pyproject else 0
    )
    repo.local_modules = {
        path.stem for path in python_files(root, excludes) if path.stem != "__init__"
    }
    return repo


def line_text(root: Path, rel: str, line: int) -> str:
    path = root / rel
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").split("\n")
    except OSError:
        return ""
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()[:160]
    return ""


def _norm(name: str) -> str:
    return re.sub(r"[-_.]", "", name).lower()


def _import_candidates(dep: str) -> set[str]:
    base = normalise_dist(dep)
    names = {_norm(base)}
    alias = IMPORT_ALIASES.get(base)
    if alias:
        names.add(_norm(alias))
    head = base.split("[")[0]
    names.add(_norm(head))
    return names


# --------------------------------------------------------------------------- 1


def pair_python_requires(repo: Repo, claims: list[Claim]) -> list[Candidate]:
    if not repo.project.requires_python:
        return []
    declared = version_floor(repo.project.requires_python)
    impl = implementation(
        kind=Kind.PYTHON_REQUIRES,
        value=repo.project.requires_python,
        file="pyproject.toml",
        line=repo.project.requires_python_line or 1,
        snippet=line_text(repo.root, "pyproject.toml", repo.project.requires_python_line or 1),
        detail="declared interpreter floor",
    )

    out: list[Candidate] = []
    for claim in claims:
        promised = version_floor(claim.value)
        if promised and declared and promised != declared:
            reason = (
                f"document promises Python {promised[0]}.{promised[1]}, "
                f"packaging declares requires-python {repo.project.requires_python}"
            )
            severity = Severity.HIGH if promised < declared else Severity.LOW
        else:
            reason = "document and requires-python agree on the interpreter floor"
            severity = Severity.LOW
        out.append(
            Candidate(
                id=f"{claim.id}-py",
                kind=Kind.PYTHON_REQUIRES,
                claim=claim,
                implementation=impl,
                machine_reason=reason,
                machine_severity=severity,
                machine_drift=promised is not None and promised != declared,
            )
        )
    return out


# --------------------------------------------------------------------------- 2


def pair_dependencies(repo: Repo, claims: list[Claim]) -> list[Candidate]:
    """No prose needed: the dependency table *is* the promise."""

    if not repo.project.has_pyproject:
        return []

    declared = {normalise_dist(dep.name): dep for dep in repo.project.dependencies}
    allowed = set(declared)
    for name in _extra_dependency_names(repo):
        allowed.add(name)

    own = {_norm(name) for name in repo.project.packages}
    out: list[Candidate] = []

    declared_names: set[str] = set()
    for dep_name in declared:
        declared_names |= _import_candidates(dep_name)

    for module, ref in sorted(repo.imports.items()):
        key = _norm(module)
        if key in own or module in own:
            continue
        if module in repo.local_modules:
            continue
        if key in declared_names:
            continue
        if any(_norm(a) == key for name in allowed for a in _import_candidates(name)):
            continue
        out.append(
            Candidate(
                id=f"dep-undec-{module}",
                kind=Kind.DEPENDENCY,
                claim=_deps_block_claim(repo),
                implementation=implementation(
                    kind=Kind.DEPENDENCY,
                    value=module,
                    file=ref.file,
                    line=ref.line,
                    snippet=line_text(repo.root, ref.file, ref.line),
                    detail="imported at runtime",
                ),
                machine_reason=f"`{module}` is imported but never declared as a dependency",
                machine_severity=Severity.HIGH,
            )
        )

    unused = 0
    for dep_name, dep in declared.items():
        candidates = _import_candidates(dep_name)
        if any(_norm(module) in candidates for module in repo.imports):
            continue
        unused += 1
        if unused > MAX_FINDINGS_PER_KIND:
            continue
        out.append(
            Candidate(
                id=f"dep-unused-{dep_name}",
                kind=Kind.DEPENDENCY,
                claim=rule_claim(
                    text=repo.pyproject_text,
                    quote=dep.raw.strip(),
                    file="pyproject.toml",
                    kind=Kind.DEPENDENCY,
                    value=dep_name,
                    claim_id=f"dep-unused-{dep_name}",
                ),
                implementation=None,
                machine_reason=f"`{dep_name}` is declared but no source file imports it",
                machine_severity=Severity.LOW,
            )
        )
    return out


def _deps_block_claim(repo: Repo) -> Claim:
    line = 1
    for number, text in enumerate(repo.pyproject_text.split("\n"), start=1):
        if text.strip().startswith("dependencies"):
            line = number
            break
    return rule_claim(
        text=repo.pyproject_text,
        quote=_quote_at_line(repo.pyproject_text, line),
        file="pyproject.toml",
        kind=Kind.DEPENDENCY,
        value="dependencies",
        claim_id="dep-block",
    )


def _quote_at_line(text: str, line: int) -> str:
    lines = text.split("\n")
    if 1 <= line <= len(lines):
        return lines[line - 1].strip()
    return "[project]"


def _extra_dependency_names(repo: Repo) -> set[str]:
    names: set[str] = set()
    try:
        import tomllib

        data = tomllib.loads(repo.pyproject_text)
    except Exception:  # noqa: BLE001 - a broken toml is reported elsewhere
        return names
    project = data.get("project", {}) or {}
    for group in (project.get("optional-dependencies") or {}).values():
        for entry in group or []:
            names.add(normalise_dist(re.split(r"[<>=!~\[; ]", str(entry))[0]))
    for entry in (data.get("dependency-groups") or {}).get("dev", []) or []:
        names.add(normalise_dist(re.split(r"[<>=!~\[; ]", str(entry))[0]))
    return {name for name in names if name}


# --------------------------------------------------------------------------- 3


def pair_commands(repo: Repo, claims: list[Claim]) -> list[Candidate]:
    out: list[Candidate] = []
    for claim in claims:
        name = claim.value.strip()
        if not name or name.startswith("-"):
            continue
        ref = repo.subcommands.get(name)
        if ref is None:
            out.append(
                Candidate(
                    id=f"{claim.id}-cmd",
                    kind=Kind.COMMAND,
                    claim=claim,
                    implementation=None,
                    machine_reason=f"documented command `{name}` is not registered by any add_parser()",
                    machine_severity=Severity.HIGH,
                )
            )
        else:
            out.append(
                Candidate(
                    id=f"{claim.id}-cmd",
                    kind=Kind.COMMAND,
                    claim=claim,
                    implementation=implementation(
                        kind=Kind.COMMAND,
                        value=name,
                        file=ref.file,
                        line=ref.line,
                        snippet=line_text(repo.root, ref.file, ref.line),
                        detail="registered subcommand",
                    ),
                    machine_reason=f"`{name}` exists in the command table",
                    machine_severity=Severity.LOW,
                    machine_drift=False,
                )
            )
    return out


# --------------------------------------------------------------------------- 4


def pair_env(repo: Repo, claims: list[Claim]) -> list[Candidate]:
    out: list[Candidate] = []
    documented: set[str] = set()

    for claim in claims:
        name = claim.value.strip()
        if not name:
            continue
        documented.add(name)
        ref = repo.env_reads.get(name)
        if ref is None:
            out.append(
                Candidate(
                    id=f"{claim.id}-env",
                    kind=Kind.ENV_VAR,
                    claim=claim,
                    implementation=None,
                    machine_reason=f"document asks for `{name}` but no code path reads it",
                    machine_severity=Severity.HIGH,
                )
            )
        else:
            out.append(
                Candidate(
                    id=f"{claim.id}-env",
                    kind=Kind.ENV_VAR,
                    claim=claim,
                    implementation=implementation(
                        kind=Kind.ENV_VAR,
                        value=name,
                        file=ref.file,
                        line=ref.line,
                        snippet=line_text(repo.root, ref.file, ref.line),
                        detail="read at runtime",
                    ),
                    machine_reason=f"`{name}` is both documented and read",
                    machine_severity=Severity.LOW,
                    machine_drift=False,
                )
            )

    for name, ref in sorted(repo.env_reads.items()):
        if name in documented or not _looks_like_credential(name):
            continue
        out.append(
            Candidate(
                id=f"env-undoc-{name}",
                kind=Kind.ENV_VAR,
                claim=rule_claim(
                    text=(repo.root / ref.file).read_text(encoding="utf-8", errors="replace"),
                    quote=_quote_containing(
                        (repo.root / ref.file).read_text(encoding="utf-8", errors="replace"),
                        name,
                    ),
                    file=ref.file,
                    kind=Kind.ENV_VAR,
                    value=name,
                    claim_id=f"env-undoc-{name}",
                ),
                implementation=None,
                machine_reason=f"`{name}` is required at runtime but never mentioned in the docs",
                machine_severity=Severity.MEDIUM,
            )
        )
    return out


def _looks_like_credential(name: str) -> bool:
    return bool(re.search(r"(_API_KEY|_TOKEN|_SECRET|_KEY|_DSN|_WEBHOOK)$", name))


def _quote_containing(text: str, needle: str) -> str:
    for line in text.split("\n"):
        if needle in line:
            stripped = line.strip()
            if len(stripped) >= 8:
                return stripped
    return needle
