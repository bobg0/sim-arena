"""Action applier module for connecting one_step actions to env/actions."""

from __future__ import annotations

import copy
import logging
from pathlib import Path
from typing import Any, MutableMapping

from env.actions.trace_io import load_trace, save_trace
from env.actions.utils import ACTION_DEFAULTS, ACTION_FUNCTIONS, diff_objects

logger = logging.getLogger("action_applier")


def _format_path(path: list[Any]) -> str:
    """Format a path list as a readable string."""
    parts = []
    for p in path:
        parts.append(f"[{p}]" if isinstance(p, int) else str(p))
    return " -> ".join(parts) if parts else "root"


def _print_changes(action_type: str, deploy: str, changed: bool, diff: list[dict[str, Any]]) -> None:
    """Print a formatted summary of action changes."""
    print(f"\n{'='*60}")
    print(f"ACTION APPLIED: {action_type}")
    print(f"Deployment: {deploy}")
    print(f"{'='*60}")

    if not changed or not diff:
        print("No changes were made" if not changed else "Action reported changes but no differences detected")
        print(f"{'='*60}\n")
        return

    print(f"{len(diff)} change(s) detected:\n")
    for i, change in enumerate(diff, 1):
        path = change.get("path", [])
        before = change.get("before")
        after = change.get("after")
        path_str = _format_path(path)

        print(f"  Change {i}:")
        print(f"    Location: {path_str}")
        if before is None:
            print(f"    Added: {after}")
        elif after is None:
            print(f"    Removed: {before}")
        else:
            print(f"    Modified: {before} -> {after}")
            # Show summary for common fields
            if path and isinstance(path[-1], str):
                field = path[-1]
                if field == "cpu" and before and after:
                    print(f"    CPU request changed from {before} to {after}")
                elif field == "memory" and before and after:
                    print(f"    Memory request changed from {before} to {after}")
                elif field == "replicas":
                    print(f"    Replica count changed from {before} to {after}")
        if i < len(diff):
            print()
    print(f"{'='*60}\n")


def apply_action(
    trace_obj: MutableMapping[str, Any],
    action: dict[str, Any],
    deploy: str,
) -> tuple[MutableMapping[str, Any], dict[str, Any]]:
    """Apply an action to a trace object and return the modified trace with change info."""
    action_type = action.get("type", "noop")

    if action_type == "noop":
        info = {"changed": False, "op": "noop", "deploy": deploy, "diff": []}
        _print_changes("noop", deploy, False, [])
        return copy.deepcopy(trace_obj), info

    if action_type not in ACTION_FUNCTIONS:
        raise ValueError(
            f"Unknown action type '{action_type}'. "
            f"Available: {', '.join(sorted(ACTION_FUNCTIONS.keys()))}, 'noop'"
        )

    action_fn = ACTION_FUNCTIONS[action_type]
    defaults = ACTION_DEFAULTS.get(action_type, {})
    kwargs: dict[str, Any] = {}

    if action_type in ("bump_cpu_small", "bump_mem_small"):
        kwargs["step"] = action.get("step", defaults.get("step"))
    elif action_type == "scale_up_replicas":
        kwargs["delta"] = action.get("delta", defaults.get("delta"))

    before_trace = copy.deepcopy(trace_obj)
    after_trace = copy.deepcopy(trace_obj)
    changed = action_fn(after_trace, deploy, **kwargs)
    diff = diff_objects(before_trace, after_trace)

    info = {"changed": changed, "op": action_type, "deploy": deploy, "diff": diff}
    _print_changes(action_type, deploy, changed, diff)

    return after_trace, info


def apply_action_from_policy(
    trace_path: str,
    action: dict[str, Any],
    deploy: str,
    output_path: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """Convenience function to apply an action from a policy decision."""
    trace_obj = load_trace(trace_path)
    modified_trace, info = apply_action(trace_obj, action, deploy)

    if output_path is None:
        tmp_dir = Path(".tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        output_path = str(tmp_dir / "trace-next.msgpack")

    save_trace(modified_trace, output_path)
    logger.info(f"Saved trace to {output_path}")
    return output_path, info