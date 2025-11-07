"""Utilities for loading and saving SimArena traces in MessagePack format."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Mapping

import json
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


def json_to_msgpack(json_path: str, output_path: str | None = None) -> str:
    """Convert a JSON trace into MessagePack and return the destination path."""

    src = Path(json_path)
    if not src.exists():
        raise FileNotFoundError(f"JSON trace not found: {src}")

    with src.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, Mapping):
        raise ValueError("JSON trace root must be a mapping")

    dst = Path(output_path) if output_path else src.with_suffix(".msgpack")
    save_trace(data, str(dst))
    return str(dst)

