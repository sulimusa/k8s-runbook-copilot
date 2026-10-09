"""Markdown/MDX -> clean Document. Removes Hugo shortcodes, HTML comments and JSX noise."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_FRONTMATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_GLOSSARY = re.compile(r'\{\{<\s*glossary_tooltip[^>]*?text="([^"]+)"[^>]*>\}\}')
_SHORTCODE = re.compile(r"\{\{[<%].*?[>%]\}\}", re.DOTALL)
_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_JSX_LINE = re.compile(r"^\s*</?[A-Z][A-Za-z0-9.]*[^>]*>\s*$")
_FENCE = re.compile(r"^\s*(```|~~~)")


@dataclass
class Document:
    path: str  # relative to the source root in the repo
    title: str
    body: str
    frontmatter: dict


def _clean(text: str) -> str:
    text = _HTML_COMMENT.sub("", text)
    text = _GLOSSARY.sub(r"\1", text)
    text = _SHORTCODE.sub("", text)
    out, in_fence = [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            in_fence = not in_fence
            out.append(line)
            continue
        if not in_fence:
            if re.match(r"^\s*(import|export)\s", line):
                continue
            if _JSX_LINE.match(line):
                continue
        out.append(line)
    cleaned = "\n".join(out)
    return re.sub(r"\n{3,}", "\n\n", cleaned).strip()


def parse_markdown(raw: str, path: str) -> Document:
    fm: dict = {}
    m = _FRONTMATTER.match(raw)
    if m:
        try:
            loaded = yaml.safe_load(m.group(1))
            fm = loaded if isinstance(loaded, dict) else {}
        except yaml.YAMLError:
            fm = {}
        raw = raw[m.end():]
    body = _clean(raw)
    title = str(fm.get("title") or "").strip()
    if not title:
        h1 = re.search(r"^#\s+(.+)$", body, re.MULTILINE)
        title = h1.group(1).strip() if h1 else Path(path).stem.replace("-", " ").title()
    return Document(path=path, title=title, body=body, frontmatter=fm)


def parse_file(file: Path, rel_path: str) -> Document:
    return parse_markdown(file.read_text(encoding="utf-8", errors="replace"), rel_path)
