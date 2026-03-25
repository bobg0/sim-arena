#!/usr/bin/env python3
"""
worker.py — Polls S3 for job manifests, runs train.py, uploads results.

Run on each EC2 instance after sourcing the environment:

    source ~/.bashrc && source ~/work/sim-arena/.venv/bin/activate
    cd ~/work/sim-arena
    python protocol/worker.py --bucket diya-simarena-jobs

The worker will loop forever: pick up a pending job → run it → write results → repeat.
Pass --run-once to process one job and exit (useful for testing).

Required env vars (same as train.py):
    AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION
    SIM_ARENA_DRIVER_TIMEOUT, SIM_ARENA_DEPLOY_TIMEOUT, SIM_ARENA_NODE_DATA_DIR
"""

import argparse
import dataclasses
import json
import logging
import os
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from protocol.schemas import JobManifest, JobResult
from protocol.s3_helpers import (
    download_file, list_keys, object_exists, put_json, upload_file, s3_uri_to_bucket_key
)

logger = logging.getLogger("worker")

PROJECT_ROOT = Path(__file__).parent.parent

# Map agent name → checkpoint file extension (mirrors train.py logic)
_AGENT_EXT = {"dqn": ".pt", "greedy": ".json", "random": ".json"}


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _worker_id() -> str:
    """Return EC2 instance ID if available, otherwise hostname."""
    try:
        token_req = urllib.request.Request(
            "http://169.254.169.254/latest/api/token",
            headers={"X-aws-ec2-metadata-token-ttl-seconds": "21600"},
            method="PUT",
        )
        with urllib.request.urlopen(token_req, timeout=2) as r:
            token = r.read().decode()
        req = urllib.request.Request(
            "http://169.254.169.254/latest/meta-data/instance-id",
            headers={"X-aws-ec2-metadata-token": token},
        )
        with urllib.request.urlopen(req, timeout=2) as r:
            return r.read().decode().strip()
    except Exception:
        return socket.gethostname()


def _ext_for_agent(agent: str) -> str:
    return _AGENT_EXT.get(agent, ".pt")


def _extract_metrics(ckpt_path: Path, agent: str) -> Tuple[int, Optional[float], Optional[float]]:
    """
    Load a checkpoint and return (episodes_completed, total_reward, final_reward).
    Works for both .pt (DQN) and .json (greedy/random) checkpoints.
    """
    try:
        if agent == "dqn":
            import torch
            data = torch.load(str(ckpt_path), map_location="cpu", weights_only=False)
            history = data.get("episode_reward_history", [])
        else:
            with open(ckpt_path) as f:
                data = json.load(f)
            history = data.get("episode_reward_history", [])

        if not history:
            return 0, None, None
        return len(history), round(sum(history), 4), round(history[-1], 4)
    except Exception as e:
        logger.warning(f"Could not extract metrics from {ckpt_path}: {e}")
        return 0, None, None


def run_job(manifest: JobManifest, worker_id: str, bucket: str) -> JobResult:
    """
    Execute one job:
      1. Download weights from S3 (if provided)
      2. Run train.py via subprocess with a timeout
      3. Upload checkpoint + log to S3
      4. Return a JobResult (success, failed, or timeout)
    """
    started_at = _now_iso()
    t0 = time.time()

    job_dir = PROJECT_ROOT / ".jobs" / manifest.job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    ext = _ext_for_agent(manifest.agent)
    save_path = job_dir / f"checkpoint_final{ext}"
    log_path = job_dir / "train.log"

    weights_path: Optional[str] = None

    try:
        # --- 1. Download initial weights ---
        if manifest.weights_s3_uri:
            w_bucket, w_key = s3_uri_to_bucket_key(manifest.weights_s3_uri)
            w_ext = Path(w_key).suffix or ext
            weights_path = str(job_dir / f"weights{w_ext}")
            logger.info(f"Downloading weights: {manifest.weights_s3_uri}")
            download_file(w_bucket, w_key, weights_path)

        # --- 2. Build train.py command ---
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "runner" / "train.py"),
            "--trace", manifest.trace_s3_uri,
            "--ns", manifest.namespace,
            "--deploy", manifest.deploy,
            "--target", str(manifest.target),
            "--agent", manifest.agent,
            "--episodes", str(manifest.episodes),
            "--steps", str(manifest.steps),
            "--duration", str(manifest.duration),
            "--save", str(save_path),
            "--log-to-terminal",
        ]
        if weights_path:
            cmd += ["--load", weights_path, "--transfer"]

        logger.info(f"Running train.py for job {manifest.job_id}")
        logger.debug("Command: %s", " ".join(cmd))

        # --- 3. Run with timeout ---
        env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
        with open(log_path, "w") as log_f:
            proc = subprocess.run(
                cmd,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=manifest.timeout_seconds,
                cwd=str(PROJECT_ROOT),
                env=env,
            )

        if proc.returncode != 0:
            raise RuntimeError(f"train.py exited with code {proc.returncode}")

        # --- 4. Upload checkpoint + log ---
        result_prefix = f"results/{manifest.job_id}"
        checkpoint_s3_uri: Optional[str] = None
        log_s3_uri: Optional[str] = None

        if save_path.exists():
            ckpt_key = f"{result_prefix}/checkpoint_final{ext}"
            upload_file(str(save_path), bucket, ckpt_key)
            checkpoint_s3_uri = f"s3://{bucket}/{ckpt_key}"
            logger.info(f"Uploaded checkpoint → {checkpoint_s3_uri}")
        else:
            logger.warning(f"Expected checkpoint not found at {save_path}")

        if log_path.exists():
            log_key = f"{result_prefix}/train.log"
            upload_file(str(log_path), bucket, log_key)
            log_s3_uri = f"s3://{bucket}/{log_key}"

        # --- 5. Extract metrics from checkpoint ---
        episodes, total_reward, final_reward = (
            _extract_metrics(save_path, manifest.agent) if save_path.exists() else (0, None, None)
        )

        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="success",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            episodes_completed=episodes,
            total_reward=total_reward,
            final_reward=final_reward,
            checkpoint_s3_uri=checkpoint_s3_uri,
            log_s3_uri=log_s3_uri,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Job {manifest.job_id} timed out after {manifest.timeout_seconds}s")
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="timeout",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"Timed out after {manifest.timeout_seconds}s",
        )

    except Exception as e:
        logger.exception(f"Job {manifest.job_id} failed: {e}")
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="failed",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=str(e),
        )


def poll_and_run(
    bucket: str,
    worker_id: str,
    poll_interval: int = 30,
    run_once: bool = False,
) -> None:
    """
    Main loop: scan S3 for pending jobs, claim one, run it, write the result.

    Claiming is best-effort (write a marker then check it's still ours).
    Two workers could theoretically run the same job — the central server
    should deduplicate by job_id when collecting results.
    """
    logger.info(
        f"Worker {worker_id} started. Bucket: s3://{bucket}, poll every {poll_interval}s"
    )

    while True:
        pending_keys = list_keys(bucket, "jobs/pending/")
        manifest_keys = [k for k in pending_keys if k.endswith("/manifest.json")]

        ran_something = False
        for key in manifest_keys:
            # key shape: jobs/pending/<job_id>/manifest.json
            job_id = key.split("/")[2]

            # Skip already-finished jobs
            if object_exists(bucket, f"results/{job_id}/result.json"):
                logger.debug(f"Job {job_id}: already done, skipping.")
                continue

            # Best-effort claim: write marker, verify it's ours
            claim_key = f"jobs/in_progress/{job_id}/claimed_by"
            if object_exists(bucket, claim_key):
                logger.debug(f"Job {job_id}: already claimed, skipping.")
                continue

            put_json(bucket, claim_key, {"worker_id": worker_id, "claimed_at": _now_iso()})
            time.sleep(1)  # brief pause so other workers can also write
            try:
                claimed_by = bucket  # placeholder — re-read to verify
                import json as _json
                from protocol.s3_helpers import get_json
                data = get_json(bucket, claim_key)
                if data.get("worker_id") != worker_id:
                    logger.info(f"Job {job_id}: lost claim race, skipping.")
                    continue
            except Exception:
                logger.warning(f"Could not verify claim for job {job_id}, proceeding anyway.")

            manifest_data = _load_manifest(bucket, key)
            if manifest_data is None:
                continue

            logger.info(f"Starting job {job_id}")
            result = run_job(manifest_data, worker_id, bucket)

            # Write result.json
            put_json(bucket, f"results/{job_id}/result.json", dataclasses.asdict(result))
            logger.info(f"Job {job_id} → status={result.status}, episodes={result.episodes_completed}")

            ran_something = True
            if run_once:
                return

        if not ran_something:
            if run_once:
                logger.info("No pending jobs found (--run-once).")
                return
            logger.info(f"No pending jobs. Sleeping {poll_interval}s …")
            time.sleep(poll_interval)


def _load_manifest(bucket: str, key: str) -> Optional[JobManifest]:
    try:
        from protocol.s3_helpers import get_json
        data = get_json(bucket, key)
        return JobManifest.from_dict(data)
    except Exception as e:
        logger.error(f"Could not load manifest {key}: {e}")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Sim-arena EC2 worker: polls S3 for jobs and runs train.py"
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("JOBS_BUCKET", "diya-simarena-jobs"),
        help="S3 bucket for job manifests and results (default: diya-simarena-jobs)",
    )
    parser.add_argument(
        "--worker-id",
        default=None,
        help="Worker identifier (default: EC2 instance ID or hostname)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=30,
        help="Seconds to wait between S3 polls when idle (default: 30)",
    )
    parser.add_argument(
        "--run-once",
        action="store_true",
        help="Process one job then exit — useful for testing",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [worker] %(message)s",
        stream=sys.stdout,
    )

    worker_id = args.worker_id or _worker_id()
    poll_and_run(args.bucket, worker_id, args.poll_interval, args.run_once)


if __name__ == "__main__":
    main()
