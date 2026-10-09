"""Fetch public sources with git at PINNED commits (sparse, blobless, depth 1).

Why git instead of scraping: reproducible (commit SHA), polite, license files come with it.
"""
from __future__ import annotations

import datetime as dt
import json
import re

# only fixed git invocations, inputs validated below
import subprocess  # nosec B404
import sys

from ..config import get_settings
from .sources import Source, load_sources


def _git(cwd, *args: str) -> str:
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)  # nosec B603 B607
    if r.returncode != 0:
        raise RuntimeError(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout.strip()


_SHA = re.compile(r"[0-9a-f]{40}")


def _validate(src: Source) -> None:
    """sources.yaml is trusted config, but never let a typo become a git argument (e.g. a leading '-')."""
    if not (src.commit and _SHA.fullmatch(src.commit)):
        raise ValueError(f"{src.id}: commit must be a full 40-char lowercase SHA")
    if not (src.repo and src.repo.startswith("https://")):
        raise ValueError(f"{src.id}: repo must be an https:// URL")
    if any(p.startswith("-") for p in src.paths):
        raise ValueError(f"{src.id}: sparse paths must not start with '-'")


def fetch_source(src: Source, raw_dir) -> dict:
    _validate(src)
    dest = raw_dir / src.id
    dest.mkdir(parents=True, exist_ok=True)
    if not (dest / ".git").exists():
        _git(dest, "init", "-q")
        _git(dest, "remote", "add", "origin", src.repo)
    current = None
    try:
        current = _git(dest, "rev-parse", "HEAD")
    except RuntimeError:
        pass
    if current != src.commit:
        _git(dest, "fetch", "-q", "--depth", "1", "--filter=blob:none", "origin", src.commit)
        _git(dest, "sparse-checkout", "init", "--no-cone")
        _git(dest, "sparse-checkout", "set", "--no-cone", *src.paths)
        _git(dest, "checkout", "-q", "FETCH_HEAD")
    sha = _git(dest, "rev-parse", "HEAD")
    return {"id": src.id, "repo": src.repo, "commit": sha, "license": src.license,
            "fetched_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")}


def main() -> int:
    s = get_settings()
    s.raw_dir.mkdir(parents=True, exist_ok=True)
    lock = {}
    for src in load_sources(s):
        if not src.is_remote:
            continue
        if not src.commit:
            print(f"[skip] {src.id}: no pinned commit in sources.yaml", file=sys.stderr)
            continue
        print(f"[fetch] {src.id} @ {src.commit[:10]} ...")
        lock[src.id] = fetch_source(src, s.raw_dir)
    s.lock_file.write_text(json.dumps(lock, indent=2))
    print(f"wrote {s.lock_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
