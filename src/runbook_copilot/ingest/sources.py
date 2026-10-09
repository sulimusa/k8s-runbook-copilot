from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from ..config import Settings, get_settings


@dataclass
class Source:
    id: str
    license: str
    url_base: str
    description: str = ""
    repo: str | None = None
    commit: str | None = None
    root: str = ""
    local_path: str | None = None
    lowercase_url: bool = False
    paths: list[str] = field(default_factory=list)
    enabled: bool = True

    @property
    def is_remote(self) -> bool:
        return self.repo is not None


def load_sources(settings: Settings | None = None, only_enabled: bool = True) -> list[Source]:
    s = settings or get_settings()
    raw = yaml.safe_load(s.sources_file.read_text())["sources"]
    out = [Source(**r) for r in raw]
    return [x for x in out if x.enabled] if only_enabled else out


def load_lock(settings: Settings | None = None) -> dict:
    s = settings or get_settings()
    if s.lock_file.exists():
        return json.loads(s.lock_file.read_text())
    return {}


def source_dir(src: Source, settings: Settings | None = None) -> Path:
    s = settings or get_settings()
    if src.local_path:
        return s.root / src.local_path
    return s.raw_dir / src.id
