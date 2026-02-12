#!/usr/bin/env python3
"""Convert JSON trace to MessagePack. Thin wrapper around env.actions.trace_io.json_to_msgpack."""
import sys
from pathlib import Path

# Add project root for imports
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from env.actions.trace_io import json_to_msgpack


def main():
    if len(sys.argv) < 3:
        print("Usage: python json2msg.py <input.json> <output.msgpack>")
        sys.exit(1)
    input_json = sys.argv[1]
    output_msgpack = sys.argv[2]
    json_to_msgpack(input_json, output_msgpack)
    print(f"Converted {input_json} → {output_msgpack}")


if __name__ == "__main__":
    main()
