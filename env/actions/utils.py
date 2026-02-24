"""Shared utilities for action modules."""

from __future__ import annotations

from typing import Any, Callable

from .ops import bump_cpu_small, bump_mem_small, scale_up_replicas

# Map action types to their corresponding functions
ACTION_FUNCTIONS: dict[str, Callable[..., bool]] = {
    "bump_cpu_small": bump_cpu_small,
    "bump_mem_small": bump_mem_small,
    "scale_up_replicas": scale_up_replicas,
}

# Default parameters for actions
ACTION_DEFAULTS: dict[str, dict[str, Any]] = {
    "bump_cpu_small": {"step": "500m"},
    "bump_mem_small": {"step": "256Mi"},
    "scale_up_replicas": {"delta": 1},
}

_MISSING = object()


def diff_objects(before: Any, after: Any, path: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    """Compute a deep diff between two objects, returning a list of changes."""
    if before is _MISSING:
        return [{"path": list(path), "before": None, "after": after}]
    if after is _MISSING:
        return [{"path": list(path), "before": before, "after": None}]

    if isinstance(before, dict) and isinstance(after, dict):
        out: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after), key=str):
            out.extend(diff_objects(
                before.get(key, _MISSING),
                after.get(key, _MISSING),
                path + (key,)
            ))
        return out

    if isinstance(before, list) and isinstance(after, list):
        out: list[dict[str, Any]] = []
        for idx, (b_item, a_item) in enumerate(zip(before, after)):
            out.extend(diff_objects(b_item, a_item, path + (idx,)))
        if len(before) != len(after):
            longer, marker = (before, "before") if len(before) > len(after) else (after, "after")
            for idx in range(min(len(before), len(after)), len(longer)):
                entry = {"path": list(path + (idx,)), "before": None, "after": None}
                entry[marker] = longer[idx]
                out.append(entry)
        return out

    if before != after:
        return [{"path": list(path), "before": before, "after": after}]
    return []

