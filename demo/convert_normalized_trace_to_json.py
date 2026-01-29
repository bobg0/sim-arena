#!/usr/bin/env python3
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env.actions.trace_io import load_trace


def main() -> None:
    demo_dir = Path(__file__).parent
    src = demo_dir / "trace-normalized.msgpack"
    dst = demo_dir / "trace-normalized.json"

    trace = load_trace(str(src))
    dst.write_text(json.dumps(trace, indent=2), encoding="utf-8")
    print(f"Wrote {dst}")


if __name__ == "__main__":
    main()
