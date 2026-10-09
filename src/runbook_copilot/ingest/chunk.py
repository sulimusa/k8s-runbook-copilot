"""Heading-aware chunking.

Rules (simple on purpose):
  1. Split a document at markdown headings (H1-H4), never inside code fences.
  2. Sections shorter than `min_words` are merged into the next section.
  3. Sections longer than `max_words` are split on blank lines (code blocks stay whole when possible).
  4. Chunk ids are stable: "<source_id>:<doc path without extension>#<nn>".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from ..schemas import Chunk
from .parse import Document
from .tags import tag_text

_HEADING = re.compile(r"^(#{1,4})\s+(.*\S)\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class _Section:
    path: str
    lines: list[str]

    @property
    def text(self) -> str:
        return "\n".join(self.lines).strip()

    @property
    def words(self) -> int:
        return len(self.text.split())


def _sections(doc: Document) -> list[_Section]:
    sections: list[_Section] = [_Section(doc.title, [])]
    stack: list[tuple[int, str]] = []
    in_fence = False
    for line in doc.body.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        m = None if in_fence else _HEADING.match(line)
        if m:
            level, title = len(m.group(1)), m.group(2)
            stack = [(lv, t) for lv, t in stack if lv < level] + [(level, title)]
            path = " > ".join([doc.title] + [t for _, t in stack if t != doc.title])
            sections.append(_Section(path, [line]))
        else:
            sections[-1].lines.append(line)
    return [s for s in sections if s.text]


def _blocks(text: str) -> list[str]:
    blocks, cur, in_fence = [], [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
        cur.append(line)
        if not in_fence and not line.strip():
            blocks.append("\n".join(cur).strip())
            cur = []
    if cur:
        blocks.append("\n".join(cur).strip())
    return [b for b in blocks if b]


def _split_big(text: str, max_words: int) -> list[str]:
    pieces: list[str] = []
    cur: list[str] = []
    count = 0

    def flush() -> None:
        nonlocal cur, count
        if cur:
            pieces.append("\n\n".join(cur))
        cur, count = [], 0

    for block in _blocks(text):
        w = len(block.split())
        if w > max_words * 2:  # one huge block (e.g. giant YAML): hard split by lines
            flush()
            buf: list[str] = []
            n = 0
            for line in block.splitlines():
                buf.append(line)
                n += len(line.split())
                if n >= max_words:
                    pieces.append("\n".join(buf))
                    buf, n = [], 0
            if buf:
                pieces.append("\n".join(buf))
            continue
        if count + w > max_words and cur:
            flush()
        cur.append(block)
        count += w
    flush()
    return pieces


def chunk_document(doc: Document, *, source_id: str, url: str, license: str, commit_sha: str,
                   max_words: int = 350, min_words: int = 60) -> list[Chunk]:
    merged: list[_Section] = []
    carry: _Section | None = None
    for sec in _sections(doc):
        if carry:
            sec = _Section(sec.path, carry.lines + [""] + sec.lines)  # keep the path of the larger, later section
            carry = None
        if sec.words < min_words:
            carry = sec
            continue
        merged.append(sec)
    if carry:
        if merged:
            merged[-1].lines += [""] + carry.lines
        else:
            merged.append(carry)

    stem = re.sub(r"\.(md|mdx)$", "", doc.path)
    chunks: list[Chunk] = []
    for sec in merged:
        for piece in (_split_big(sec.text, max_words) if sec.words > max_words else [sec.text]):
            n = len(chunks)
            chunks.append(Chunk(
                chunk_id=f"{source_id}:{stem}#{n:02d}", source_id=source_id, doc_path=doc.path,
                url=url, title=doc.title, heading_path=sec.path, text=piece, license=license,
                commit_sha=commit_sha, tags=tag_text(doc.title + " " + piece),
            ))
    return chunks
