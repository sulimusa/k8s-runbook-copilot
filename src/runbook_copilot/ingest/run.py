"""fetch -> parse -> chunk -> data/processed/chunks.jsonl

Usage: python -m runbook_copilot.ingest.run [--skip-fetch]
"""
from __future__ import annotations

import argparse
import json
import re
import sys

from ..config import get_settings
from .chunk import chunk_document
from .fetch import main as fetch_main
from .parse import parse_file
from .sources import Source, load_lock, load_sources, source_dir

MIN_DOC_WORDS = 40  # skips empty _index.md style pages


def _is_wanted(rel_to_repo: str, src: Source) -> bool:
    if not src.paths:
        return True
    return any(rel_to_repo == p or (p.endswith("/") and rel_to_repo.startswith(p)) for p in src.paths)


def _url_for(rel_to_root: str, src: Source) -> str:
    p = re.sub(r"\.(md|mdx)$", "", rel_to_root)
    p = re.sub(r"(^|/)_index$", "", p)
    if src.lowercase_url:
        p = p.lower()
    return src.url_base + p + "/"


def collect(settings=None) -> tuple[list, dict]:
    s = settings or get_settings()
    lock = load_lock(s)
    all_chunks, stats = [], {}
    for src in load_sources(s):
        base = source_dir(src, s)
        if not base.exists():
            print(f"[warn] {src.id}: {base} missing (run fetch / capture first)", file=sys.stderr)
            continue
        sha = lock.get(src.id, {}).get("commit") or src.commit or "local"
        files = sorted(list(base.rglob("*.md")) + list(base.rglob("*.mdx")))
        n_docs = 0
        for f in files:
            rel_repo = f.relative_to(base).as_posix()
            if src.is_remote and not _is_wanted(rel_repo, src):
                continue
            rel_root = rel_repo
            if src.root and rel_repo.startswith(src.root + "/"):
                rel_root = rel_repo[len(src.root) + 1:]
            doc = parse_file(f, rel_root)
            if len(doc.body.split()) < MIN_DOC_WORDS or doc.frontmatter.get("draft") is True:
                continue
            url = _url_for(rel_root, src) if src.is_remote else src.url_base + rel_root
            all_chunks += chunk_document(doc, source_id=src.id, url=url, license=src.license, commit_sha=sha)
            n_docs += 1
        stats[src.id] = {"docs": n_docs, "chunks": sum(1 for c in all_chunks if c.source_id == src.id)}
    return all_chunks, stats


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--skip-fetch", action="store_true")
    args = ap.parse_args()
    s = get_settings()
    if not args.skip_fetch:
        fetch_main()
    chunks, stats = collect(s)
    s.chunks_path.parent.mkdir(parents=True, exist_ok=True)
    with s.chunks_path.open("w") as fh:
        for c in chunks:
            fh.write(c.model_dump_json() + "\n")
    print(json.dumps(stats, indent=2))
    print(f"wrote {len(chunks)} chunks -> {s.chunks_path}")
    return 0 if chunks else 1


if __name__ == "__main__":
    raise SystemExit(main())
