"""Msgpack helpers used by the protocol worker (experience aggregation)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import msgpack


def read_msgpack(path: str) -> dict[str, Any]:
    raw = Path(path).read_bytes()
    return msgpack.unpackb(raw, raw=False)


def write_msgpack(path: str | Path, obj: Any) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(msgpack.packb(obj, use_bin_type=True))
