#!/usr/bin/env python3
"""Composable action helpers for SimArena traces.

The module now exposes :func:`make_action`, which mirrors the return shape of a
Gym ``Env.step`` call: ``next_state, reward, done, info``. This lets agents call
the same safe mutation logic that the CLI uses without shelling out.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path
from typing import Any, Callable, Mapping

from env.actions.ops import bump_cpu_small, bump_mem_small, scale_up_replicas
from env.actions.trace_io import load_trace, save_trace


ActionFn = Callable[[dict[str, Any]], tuple[dict[str, Any], float, bool, dict[str, Any]]]

OPS: dict[str, Callable[..., bool]] = {
    "bump_cpu_small": bump_cpu_small,
    "bump_mem_small": bump_mem_small,
    "scale_up_replicas": scale_up_replicas,
}

AVAILABLE_ACTIONS: tuple[str, ...] = tuple(sorted(OPS))

_MISSING = object()


def _diff(before: Any, after: Any, path: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    if before is _MISSING:
        return [{"path": path, "before": None, "after": after}]
    if after is _MISSING:
        return [{"path": path, "before": before, "after": None}]

    if isinstance(before, Mapping) and isinstance(after, Mapping):
        out: list[dict[str, Any]] = []
        for key in sorted(set(before) | set(after), key=str):
            out.extend(_diff(before.get(key, _MISSING), after.get(key, _MISSING), path + (key,)))
        return out

    if isinstance(before, list) and isinstance(after, list):
        out: list[dict[str, Any]] = []
        for idx, (b_item, a_item) in enumerate(zip(before, after)):
            out.extend(_diff(b_item, a_item, path + (idx,)))
        if len(before) != len(after):
            longer, marker = (before, "before") if len(before) > len(after) else (after, "after")
            for idx in range(min(len(before), len(after)), len(longer)):
                entry = {"path": path + (idx,), "before": None, "after": None}
                entry[marker] = longer[idx]
                out.append(entry)
        return out

    if before != after:
        return [{"path": path, "before": before, "after": after}]
    return []


def make_action(op: str, deploy: str, *, step: str | None = None, delta: int | None = None) -> ActionFn:
    """Return a callable that applies *op* to a trace.

    The returned function expects a trace mapping and yields ``(next_trace, reward,
    done, info)`` to match the Gym ``Env.step`` convention. ``next_trace`` is a
    deep copy of the input with the mutation applied; the original stays intact.
    ``reward`` defaults to ``1.0`` when the action reports a change, else ``0.0``.
    ``done`` is always ``False`` because a single edit never terminates the task.
    The ``info`` dict includes a boolean ``changed`` flag and a structured diff.
    """

    if op not in OPS:
        raise ValueError(f"Unknown action '{op}'. Choices: {', '.join(AVAILABLE_ACTIONS)}")

    op_fn = OPS[op]

    kwargs: dict[str, Any] = {}
    if step is not None:
        if op not in {"bump_cpu_small", "bump_mem_small"}:
            raise ValueError("'step' only applies to bump_cpu_small or bump_mem_small")
        kwargs["step"] = step
    if delta is not None:
        if op != "scale_up_replicas":
            raise ValueError("'delta' only applies to scale_up_replicas")
        kwargs["delta"] = delta

    def _apply(trace: Mapping[str, Any]) -> tuple[dict[str, Any], float, bool, dict[str, Any]]:
        before = copy.deepcopy(trace)
        after = copy.deepcopy(trace)
        changed = op_fn(after, deploy, **kwargs)
        diff_entries = _diff(before, after)
        info = {"changed": changed, "op": op, "deploy": deploy, "diff": diff_entries}
        reward = 1.0 if changed else 0.0
        return after, reward, False, info

    return _apply


def _main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="sk-action")
    subparsers = parser.add_subparsers(dest="command", required=True)

    apply_parser = subparsers.add_parser("apply", help="Apply a safe mutation to a trace")
    apply_parser.add_argument("--in", dest="in_path", required=True, help="Input MessagePack trace")
    apply_parser.add_argument("--out", dest="out_path", required=True, help="Destination MessagePack trace")
    apply_parser.add_argument("--deploy", required=True, help="Deployment name to mutate")
    apply_parser.add_argument("--op", choices=sorted(OPS), required=True, help="Operation to run")
    apply_parser.add_argument("--step", help="Override default CPU/memory step")
    apply_parser.add_argument("--delta", type=int, help="Replica increment for scaling ops")

    args = parser.parse_args(argv)

    if args.command != "apply":
        parser.error("Unknown command")

    try:
        action = make_action(
            args.op,
            args.deploy,
            step=args.step,
            delta=args.delta,
        )
    except ValueError as exc:
        parser.error(str(exc))
        return 2

    input_trace = load_trace(args.in_path)
    next_trace, reward, _done, info = action(input_trace)
    output_path = Path(args.out_path)

    if not info["changed"]:
        save_trace(input_trace, output_path)
        print(json.dumps({"changed": False, "reward": reward, "info": info}, indent=2))
        return 1

    save_trace(next_trace, output_path)
    print(json.dumps({"changed": True, "reward": reward, "info": info}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())

