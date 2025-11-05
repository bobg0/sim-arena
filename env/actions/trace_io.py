"""Utilities for loading and saving SimArena traces in MessagePack format."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import msgpack


def load_trace(path: str) -> dict[str, Any]:
    """Load a trace from *path*.

    Parameters
    ----------
    path:
        Location of the MessagePack file on disk.

    Returns
    -------
    dict
        Parsed trace object.
    """

    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"Trace not found: {src}")

    with src.open("rb") as fh:
        data = msgpack.load(fh, raw=False)

    if not isinstance(data, dict):
        raise ValueError("Trace root must be a mapping")

    return data


def save_trace(obj: Mapping[str, Any], path: str) -> None:
    """Persist *obj* to *path* as MessagePack."""

    if not isinstance(obj, Mapping):
        raise TypeError("Trace object must be a mapping")

    dst = Path(path)
    os.makedirs(dst.parent, exist_ok=True)

    with dst.open("wb") as fh:
        msgpack.dump(dict(obj), fh, use_bin_type=True)

