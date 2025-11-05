#!/usr/bin/env python3
"""Utility to pack the synthetic demo trace into MessagePack."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from env.actions.trace_io import save_trace


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", default="demo/trace-0001.json", help="Path to the source JSON trace")
    parser.add_argument(
        "--out",
        default="demo/trace-0001.msgpack",
        help="Destination for the packed MessagePack trace",
    )
    args = parser.parse_args()

    src = Path(args.json)
    if not src.exists():
        parser.error(f"Input JSON not found: {src}")

    with src.open("r", encoding="utf-8") as fh:
        data = json.load(fh)

    save_trace(data, args.out)
    print(f"Wrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

