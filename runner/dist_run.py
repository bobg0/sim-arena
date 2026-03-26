#!/usr/bin/env python3
"""
Distributed experience-collection entrypoint (worker mode).

If your team has not wired the full dist pipeline yet, this stub fails fast with
a clear message. Training jobs use runner/train.py via protocol/worker.py only.
"""

import argparse
import sys


def main() -> int:
    p = argparse.ArgumentParser(description="Distributed SimArena runner (optional)")
    p.add_argument("--mode", default="worker")
    args, _ = p.parse_known_args()
    if args.mode == "worker":
        print(
            "dist_run.py: experience_collection mode is not available in this checkout. "
            "Use job_type=training manifests (default) with protocol/worker.py.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
