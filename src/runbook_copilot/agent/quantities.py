"""Kubernetes resource quantity parsing (memory to bytes, cpu to millicores)."""
from __future__ import annotations

import re

_BIN = {"Ki": 2**10, "Mi": 2**20, "Gi": 2**30, "Ti": 2**40}
_DEC = {"k": 10**3, "K": 10**3, "M": 10**6, "G": 10**9, "T": 10**12}
_MEM = re.compile(r"^(\d+(?:\.\d+)?)(Ki|Mi|Gi|Ti|k|K|M|G|T)?$")
_CPU = re.compile(r"^(\d+(?:\.\d+)?)(m)?$")


def parse_memory(q: str | None) -> int | None:
    if q is None:
        return None
    m = _MEM.match(str(q).strip())
    if not m:
        raise ValueError(f"invalid memory quantity: {q!r}")
    num, suffix = float(m.group(1)), m.group(2)
    return int(num * (_BIN.get(suffix) or _DEC.get(suffix) or 1))


def parse_cpu(q: str | None) -> int | None:
    """Returns millicores."""
    if q is None:
        return None
    m = _CPU.match(str(q).strip())
    if not m:
        raise ValueError(f"invalid cpu quantity: {q!r}")
    num = float(m.group(1))
    return int(num if m.group(2) else num * 1000)
