"""Find the prose that makes promises, and cut it into digestible pieces."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

# Read order matters: the first file is where most promises live.
DEFAULT_DOCS = ("README.md", "README.rst", "CONTRIBUTING.md", "docs/index.md", "docs/README.md")
MAX_CHUNK_CHARS = 1100
_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


@dataclass(slots=True)
class DocFile:
    path: str
    text: str


@dataclass(slots=True)
class Chunk:
    path: str
    heading: str
    start_line: int
    text: str


def doc_files(root: Path, extra: list[str] | None = None) -> list[DocFile]:
    """README first, then whatever ``docs/`` holds, capped so a huge repo stays cheap."""

    seen: set[Path] = set()
    ordered: list[Path] = []
    for name in DEFAULT_DOCS:
        path = root / name
        if path.is_file() and path not in seen:
            seen.add(path)
            ordered.append(path)
    for name in extra or []:
        path = root / name
        if path.is_file() and path not in seen:
            seen.add(path)
            ordered.append(path)

    docs_dir = root / "docs"
    if docs_dir.is_dir():
        for path in sorted(docs_dir.glob("*.md")):
            if path.is_file() and path not in seen:
                seen.add(path)
                ordered.append(path)

    out: list[DocFile] = []
    for path in ordered[:8]:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        out.append(DocFile(path=path.relative_to(root).as_posix(), text=text))
    return out


def chunks(doc: DocFile, max_chars: int = MAX_CHUNK_CHARS) -> list[Chunk]:
    """Split by heading, then by paragraph, so each piece fits a small model's window."""

    lines = doc.text.split("\n")
    sections: list[tuple[str, int, list[str]]] = []
    heading = ""
    start = 1
    buffer: list[str] = []

    for number, line in enumerate(lines, start=1):
        match = _HEADING.match(line)
        if match:
            if buffer:
                sections.append((heading, start, buffer))
            heading = match.group(2).strip()
            start = number
            buffer = [line]
        else:
            buffer.append(line)
    if buffer:
        sections.append((heading, start, buffer))

    out: list[Chunk] = []
    for section_heading, section_start, section_lines in sections:
        body = "\n".join(section_lines).strip("\n")
        if not body.strip():
            continue
        for piece, offset in _split(body, max_chars):
            out.append(
                Chunk(
                    path=doc.path,
                    heading=section_heading,
                    start_line=section_start + offset,
                    text=piece,
                )
            )
    return out


def _split(body: str, max_chars: int) -> list[tuple[str, int]]:
    if len(body) <= max_chars:
        return [(body, 0)]

    out: list[tuple[str, int]] = []
    paragraphs = body.split("\n\n")
    buffer: list[str] = []
    size = 0
    consumed_lines = 0
    piece_start = 0

    for paragraph in paragraphs:
        paragraph_lines = paragraph.count("\n") + 1
        if size + len(paragraph) > max_chars and buffer:
            out.append(("\n\n".join(buffer), piece_start))
            piece_start = consumed_lines
            buffer = []
            size = 0
        buffer.append(paragraph)
        size += len(paragraph) + 2
        consumed_lines += paragraph_lines + 1
    if buffer:
        out.append(("\n\n".join(buffer), piece_start))
    return out
