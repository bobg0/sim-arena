"""
protocol/inspect_run.py — CLI tool to inspect a job's S3 artifacts from your Mac.

Usage:
  python protocol/inspect_run.py <job_id>           # result + step summary
  python protocol/inspect_run.py --list              # list all result prefixes
  python protocol/inspect_run.py <job_id> --steps    # dump every step (obs/action/reward)
  python protocol/inspect_run.py <job_id> --log      # stream train.log
  python protocol/inspect_run.py <job_id> --ckpt     # print checkpoint reward history
"""
import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

# Allow running from project root
sys.path.insert(0, str(Path(__file__).parent.parent))

from protocol.s3_helpers import (
    get_json,
    download_file,
    list_keys,
)

BUCKET = os.environ.get("JOBS_BUCKET", "diya-simarena-jobs-664926621123-us-east-2-an")


def list_all_runs(bucket: str) -> None:
    keys = list_keys(bucket, "results/")
    seen = set()
    for k in keys:
        parts = k.split("/")
        if len(parts) >= 2:
            prefix = parts[1]
            if prefix not in seen:
                print(prefix)
                seen.add(prefix)


def show_result(bucket: str, job_id: str) -> dict | None:
    try:
        result = get_json(bucket, f"results/{job_id}/result.json")
        print(json.dumps(result, indent=2))
        return result
    except Exception as e:
        print(f"[warn] No result.json found: {e}", file=sys.stderr)
        return None


def show_log(bucket: str, job_id: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".log", delete=False) as f:
        tmp = f.name
    try:
        download_file(bucket, f"results/{job_id}/train.log", tmp)
        print(Path(tmp).read_text())
    except Exception as e:
        print(f"[warn] No train.log found: {e}", file=sys.stderr)


def show_steps(bucket: str, job_id: str) -> None:
    with tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False) as f:
        tmp = f.name
    try:
        download_file(bucket, f"results/{job_id}/steps.jsonl", tmp)
        lines = Path(tmp).read_text().strip().splitlines()
        print(f"{'Step':>5}  {'ready':>5}  {'pending':>7}  {'total':>5}  {'action':<22}  {'reward':>8}  at_target")
        print("-" * 75)
        for i, line in enumerate(lines):
            rec = json.loads(line)
            obs = rec.get("obs", {})
            print(
                f"{i+1:>5}  {obs.get('ready','?'):>5}  {obs.get('pending','?'):>7}  "
                f"{obs.get('total','?'):>5}  {rec.get('action', {}).get('type','?'):<22}  "
                f"{rec.get('reward', 0.0):>8.4f}  {rec.get('at_target', False)}"
            )
    except Exception as e:
        print(f"[warn] No steps.jsonl found (only available for runs after the fix): {e}", file=sys.stderr)


def show_checkpoint(bucket: str, job_id: str) -> None:
    try:
        import torch
    except ImportError:
        print("[warn] torch not installed — cannot inspect .pt checkpoint")
        return

    with tempfile.NamedTemporaryFile(suffix=".pt", delete=False) as f:
        tmp = f.name
    try:
        download_file(bucket, f"results/{job_id}/checkpoint_final.pt", tmp)
        d = torch.load(tmp, map_location="cpu", weights_only=False)
        print("Keys:", list(d.keys()))
        if "episode_reward_history" in d:
            print("Episode rewards:", d["episode_reward_history"])
        if "epsilon_history" in d:
            print("Epsilon history:", d["epsilon_history"])
    except Exception as e:
        print(f"[warn] Could not load checkpoint: {e}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect sim-arena S3 job artifacts")
    parser.add_argument("job_id", nargs="?", help="Job ID (e.g. job_20260407_235626_f1d114)")
    parser.add_argument("--list", action="store_true", help="List all job IDs with results")
    parser.add_argument("--steps", action="store_true", help="Show per-step obs/action/reward table")
    parser.add_argument("--log", action="store_true", help="Stream train.log")
    parser.add_argument("--ckpt", action="store_true", help="Print checkpoint reward history")
    parser.add_argument("--bucket", default=BUCKET, help="S3 bucket name")
    args = parser.parse_args()

    if args.list:
        list_all_runs(args.bucket)
        return

    if not args.job_id:
        parser.print_help()
        sys.exit(1)

    if args.steps:
        show_steps(args.bucket, args.job_id)
    elif args.log:
        show_log(args.bucket, args.job_id)
    elif args.ckpt:
        show_checkpoint(args.bucket, args.job_id)
    else:
        show_result(args.bucket, args.job_id)


if __name__ == "__main__":
    main()
