#!/usr/bin/env python3
"""
dispatch.py — Submit jobs to S3 and check their status.

Submit a job:
    python protocol/dispatch.py submit \\
        --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \\
        --agent dqn --episodes 10 --steps 20

Submit a job with existing weights (for subsequent training rounds):
    python protocol/dispatch.py submit \\
        --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \\
        --weights s3://diya-simarena-jobs/results/<prev_job_id>/checkpoint_final.pt

List all jobs and their status:
    python protocol/dispatch.py list
"""

import argparse
import dataclasses
import os
import uuid
from datetime import datetime, timezone

from protocol.schemas import JobManifest, JobResult
from protocol.s3_helpers import put_json, object_exists, list_keys, get_json


def _job_id() -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    short = uuid.uuid4().hex[:6]
    return f"job_{ts}_{short}"


def submit_job(manifest: JobManifest, bucket: str) -> str:
    """Write manifest.json to S3. Returns the full S3 key."""
    key = f"jobs/pending/{manifest.job_id}/manifest.json"
    put_json(bucket, key, dataclasses.asdict(manifest))
    return key


def list_jobs(bucket: str) -> None:
    """Print a status table for all jobs in the bucket."""
    pending_keys = list_keys(bucket, "jobs/pending/")
    result_keys = list_keys(bucket, "results/")
    in_progress_keys = list_keys(bucket, "jobs/in_progress/")

    pending_ids = {k.split("/")[2] for k in pending_keys if k.endswith("/manifest.json")}
    done_ids = {k.split("/")[1] for k in result_keys if k.endswith("/result.json")}
    in_progress_ids = {k.split("/")[2] for k in in_progress_keys if k.endswith("/claimed_by")}

    all_ids = sorted(pending_ids | done_ids | in_progress_ids)
    if not all_ids:
        print("No jobs found.")
        return

    print(f"\n{'Job ID':<45} {'Status':<12} {'Episodes':>10} {'Total Reward':>14}")
    print("-" * 85)
    for jid in all_ids:
        if jid in done_ids:
            try:
                r = JobResult.from_dict(get_json(bucket, f"results/{jid}/result.json"))
                status = r.status
                episodes = str(r.episodes_completed) if r.episodes_completed else "-"
                reward = f"{r.total_reward:.2f}" if r.total_reward is not None else "-"
            except Exception:
                status, episodes, reward = "done(err)", "-", "-"
        elif jid in in_progress_ids:
            status, episodes, reward = "in_progress", "-", "-"
        else:
            status, episodes, reward = "pending", "-", "-"
        print(f"{jid:<45} {status:<12} {episodes:>10} {reward:>14}")
    print()


def main():
    parser = argparse.ArgumentParser(
        description="Sim-arena job dispatcher: submit jobs to S3 or check status"
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("JOBS_BUCKET", "diya-simarena-jobs"),
        help="S3 bucket for jobs/results (default: diya-simarena-jobs)",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # --- submit ---
    sub = subparsers.add_parser("submit", help="Submit a new job manifest")
    sub.add_argument("--trace", required=True, help="S3 URI of the trace file")
    sub.add_argument("--agent", default="dqn", help="Agent type (default: dqn)")
    sub.add_argument("--episodes", type=int, default=10, help="Episodes to train (default: 10)")
    sub.add_argument("--steps", type=int, default=20, help="Max steps per episode (default: 20)")
    sub.add_argument("--duration", type=int, default=40, help="Seconds per step (default: 40)")
    sub.add_argument("--namespace", default="default")
    sub.add_argument("--deploy", default="web")
    sub.add_argument("--target", type=int, default=3)
    sub.add_argument(
        "--weights",
        default=None,
        help="S3 URI of initial weights file (omit for a fresh start)",
    )
    sub.add_argument(
        "--timeout",
        type=int,
        default=3600,
        help="Max wall-clock seconds for the job (default: 3600)",
    )
    sub.add_argument("--job-id", default=None, help="Custom job ID (auto-generated if omitted)")

    # --- list ---
    subparsers.add_parser("list", help="List all jobs and their status")

    args = parser.parse_args()

    if args.command == "submit":
        manifest = JobManifest(
            job_id=args.job_id or _job_id(),
            trace_s3_uri=args.trace,
            agent=args.agent,
            episodes=args.episodes,
            steps=args.steps,
            duration=args.duration,
            namespace=args.namespace,
            deploy=args.deploy,
            target=args.target,
            weights_s3_uri=args.weights,
            timeout_seconds=args.timeout,
        )
        key = submit_job(manifest, args.bucket)
        print(f"Submitted:  {manifest.job_id}")
        print(f"Manifest:   s3://{args.bucket}/{key}")
        print(f"Trace:      {manifest.trace_s3_uri}")
        if manifest.weights_s3_uri:
            print(f"Weights:    {manifest.weights_s3_uri}")
        print(f"Agent:      {manifest.agent}  |  episodes={manifest.episodes}  steps={manifest.steps}")

    elif args.command == "list":
        list_jobs(args.bucket)


if __name__ == "__main__":
    main()
