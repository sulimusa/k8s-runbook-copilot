"""Append-only JSONL audit trail: every decision and every cluster write, with the reason and the trace id."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class AuditLog:
    def __init__(self, path: Path | None):
        self.path = path

    def write(self, run_id: str, event: str, **fields) -> None:
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        rec = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run_id": run_id, "event": event}
        for k, v in fields.items():
            rec[k] = v[:800] if isinstance(v, str) else v
        with self.path.open("a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")
