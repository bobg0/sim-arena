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
<<<<<<< HEAD
=======
import shutil
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d

import boto3
import socket
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

# Allow `python protocol/worker.py` from repo root (same pattern as runner/train.py)
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from protocol.schemas import JobManifest, JobResult
<<<<<<< HEAD
from protocol.s3_helpers import (
    download_file, list_keys, object_exists, put_json, upload_file, s3_uri_to_bucket_key
=======
from protocol.sync_paths import (
    checkpoint_ext,
    federation_from_ckpt_key,
    federation_from_done_key,
    federation_global_weights_key,
    from_worker_ckpt_key,
    from_worker_done_key,
    to_worker_weights_key,
)
from protocol.s3_helpers import (
    copy_object,
    download_file,
    list_keys,
    object_exists,
    put_json,
    upload_file,
    s3_uri_to_bucket_key,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
)
from runner.distributed import read_msgpack, write_msgpack

logger = logging.getLogger("worker")

PROJECT_ROOT = Path(__file__).parent.parent

<<<<<<< HEAD
# Map agent name → checkpoint file extension (mirrors train.py logic)
_AGENT_EXT = {"dqn": ".pt", "greedy": ".json", "random": ".json"}


=======
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
    return _AGENT_EXT.get(agent, ".pt")
=======
    return checkpoint_ext(agent)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


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


def _run_experience_collection_job(manifest: JobManifest, worker_id: str, bucket: str, job_dir: Path, started_at: str, t0: float) -> JobResult:
    """Run an experience collection job."""
    transitions_path = job_dir / "transitions.msgpack"
    log_path = job_dir / "experience_collection.log"

    try:
        weights_path: Optional[str] = None
        if manifest.weights_s3_uri:
            w_bucket, w_key = s3_uri_to_bucket_key(manifest.weights_s3_uri)
            w_ext = Path(w_key).suffix or ".pt"
            weights_path = str(job_dir / f"weights{w_ext}")
            logger.info(f"Downloading weights: {manifest.weights_s3_uri}")
            download_file(w_bucket, w_key, weights_path)

        s3_prefix = f"jobs/{manifest.job_id}"
        cmd = [
            sys.executable,
            str(PROJECT_ROOT / "runner" / "dist_run.py"),
            "--mode", "worker",
            "--s3-bucket", bucket,
            "--s3-prefix", s3_prefix,
            "--worker-id", worker_id,
            "--episodes", str(manifest.episodes),
            "--trace", manifest.trace_s3_uri,
            "--ns", manifest.namespace,
            "--target", str(manifest.target),
        ]

        if weights_path:
            cmd.extend(["--weights", weights_path])

        logger.info(f"Running experience collection for job {manifest.job_id}")
        logger.debug("Command: %s", " ".join(cmd))

        env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
        with open(log_path, "w") as log_f:
            proc = subprocess.run(
                cmd,
                env=env,
                stdout=log_f,
                stderr=subprocess.STDOUT,
                timeout=manifest.timeout_seconds,
                cwd=str(PROJECT_ROOT),
            )

        if proc.returncode != 0:
            return JobResult(
                job_id=manifest.job_id,
                worker_id=worker_id,
                status="failed",
                started_at=started_at,
                finished_at=_now_iso(),
                elapsed_seconds=round(time.time() - t0, 1),
                error=f"dist_run.py exited with code {proc.returncode}",
            )

        all_transitions = []
        s3_client = boto3.client("s3", region_name=os.environ.get("AWS_REGION"))
        paginator = s3_client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{s3_prefix}/exp/"):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".msgpack"):
                    local_file = job_dir / Path(key).name
                    s3_client.download_file(bucket, key, str(local_file))
                    exp_data = read_msgpack(str(local_file))
                    all_transitions.extend(exp_data.get("transitions", []))

        write_msgpack(transitions_path, {
            "job_id": manifest.job_id,
            "worker_id": worker_id,
            "transitions": all_transitions,
            "total_transitions": len(all_transitions),
        })

        transitions_key = f"results/{manifest.job_id}/transitions.msgpack"
        log_key = f"results/{manifest.job_id}/experience_collection.log"

        upload_file(str(transitions_path), bucket, transitions_key)
        upload_file(str(log_path), bucket, log_key)

        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="success",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            episodes_completed=manifest.episodes,
            transitions_s3_uri=f"s3://{bucket}/{transitions_key}",
            log_s3_uri=f"s3://{bucket}/{log_key}",
        )

    except subprocess.TimeoutExpired:
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="timeout",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"Job timed out after {manifest.timeout_seconds} seconds",
        )
    except Exception as e:
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="failed",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=str(e),
        )


<<<<<<< HEAD
=======
def _wait_for_server_weights(
    bucket: str,
    key: str,
    poll_interval: int,
    timeout_seconds: float,
) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if object_exists(bucket, key):
            return
        time.sleep(max(1, poll_interval))
    raise TimeoutError(
        f"Timed out after {timeout_seconds}s waiting for server weights at s3://{bucket}/{key}"
    )


def _run_training_job_per_episode_sync(
    manifest: JobManifest,
    worker_id: str,
    bucket: str,
    job_dir: Path,
    started_at: str,
    t0: float,
    ext: str,
) -> JobResult:
    """
    Run N episodes as N separate train.py processes. After each episode, upload checkpoint
    and metrics; wait for Task 3 to place the next weights under sync/to_worker/, then continue.

    If manifest.federation_group_id is set, uploads go under results/_federation/<group>/...
    and all workers wait on the same global_weights object (FedAvg produced by sync_server).
    """
    combined_log = job_dir / "train.log"
    episode_rewards: list[float] = []
    weights_path: Optional[str] = None
    fed_group = (manifest.federation_group_id or "").strip()
    use_federation = bool(fed_group)
    if use_federation and manifest.agent != "dqn":
        raise ValueError(
            "federation_group_id is only supported with agent=dqn (FedAvg over .pt checkpoints)"
        )
    if use_federation and manifest.federation_size < 1:
        raise ValueError("federation_size must be >= 1")

    try:
        if manifest.weights_s3_uri:
            w_bucket, w_key = s3_uri_to_bucket_key(manifest.weights_s3_uri)
            w_ext = Path(w_key).suffix or ext
            weights_path = str(job_dir / f"initial_weights{w_ext}")
            logger.info(f"Downloading initial weights: {manifest.weights_s3_uri}")
            download_file(w_bucket, w_key, weights_path)

        env = {**os.environ, "PYTHONPATH": str(PROJECT_ROOT)}
        save_path = job_dir / f"checkpoint_final{ext}"

        for ep in range(1, manifest.episodes + 1):
            if ep >= 2:
                if use_federation:
                    if manifest.sync_identity_server:
                        raise ValueError(
                            "sync_identity_server is not supported with federation_group_id; "
                            "run sync_server.py with FedAvg instead"
                        )
                    server_key = federation_global_weights_key(fed_group, ep, ext)
                    logger.info(
                        f"Waiting for federated global weights before episode {ep} "
                        f"(s3://{bucket}/{server_key})"
                    )
                    _wait_for_server_weights(
                        bucket,
                        server_key,
                        manifest.sync_weights_poll_interval_seconds,
                        float(manifest.sync_server_weights_timeout_seconds),
                    )
                else:
                    server_key = to_worker_weights_key(manifest.job_id, ep, ext)
                    if manifest.sync_identity_server:
                        src = from_worker_ckpt_key(manifest.job_id, ep - 1, ext)
                        logger.info(
                            f"sync_identity_server: copying s3://{bucket}/{src} → "
                            f"s3://{bucket}/{server_key}"
                        )
                        copy_object(bucket, src, server_key)
                    else:
                        logger.info(
                            f"Waiting for server weights before episode {ep} "
                            f"(s3://{bucket}/{server_key})"
                        )
                        _wait_for_server_weights(
                            bucket,
                            server_key,
                            manifest.sync_weights_poll_interval_seconds,
                            float(manifest.sync_server_weights_timeout_seconds),
                        )
                weights_path = str(job_dir / f"server_weights_ep_{ep:04d}{ext}")
                download_file(bucket, server_key, weights_path)

            round_save = job_dir / f"round_{ep:04d}_save{ext}"
            round_log = job_dir / f"train_round_{ep:04d}.log"

            cmd = [
                sys.executable,
                str(PROJECT_ROOT / "runner" / "train.py"),
                "--trace", manifest.trace_s3_uri,
                "--ns", manifest.namespace,
                "--deploy", manifest.deploy,
                "--target", str(manifest.target),
                "--agent", manifest.agent,
                "--episodes", "1",
                "--steps", str(manifest.steps),
                "--duration", str(manifest.duration),
                "--save", str(round_save),
                "--log-to-terminal",
            ]
            if weights_path:
                cmd += ["--load", weights_path, "--transfer"]

            logger.info(f"Per-episode sync: running train.py episode round {ep}/{manifest.episodes}")
            logger.debug("Command: %s", " ".join(cmd))

            with open(round_log, "w") as log_f:
                proc = subprocess.run(
                    cmd,
                    stdout=log_f,
                    stderr=subprocess.STDOUT,
                    timeout=manifest.timeout_seconds,
                    cwd=str(PROJECT_ROOT),
                    env=env,
                )

            # Append round log to combined train.log for a single S3 artifact
            if round_log.exists():
                with open(combined_log, "a") as out:
                    out.write(f"\n--- train.py round {ep}/{manifest.episodes} ---\n")
                    out.write(round_log.read_text())

            if proc.returncode != 0:
                raise RuntimeError(
                    f"train.py exited with code {proc.returncode} (episode round {ep})"
                )

            if not round_save.exists():
                raise RuntimeError(f"Missing checkpoint after episode round {ep}: {round_save}")

            if use_federation:
                ckpt_key = federation_from_ckpt_key(fed_group, ep, worker_id, ext)
            else:
                ckpt_key = from_worker_ckpt_key(manifest.job_id, ep, ext)
            upload_file(str(round_save), bucket, ckpt_key)

            e_done, _, ep_final = _extract_metrics(round_save, manifest.agent)
            if ep_final is not None:
                episode_rewards.append(float(ep_final))

            done_payload = {
                "job_id": manifest.job_id,
                "worker_id": worker_id,
                "agent": manifest.agent,
                "total_episodes": manifest.episodes,
                "episode_index": ep,
                "episodes_completed_in_checkpoint": e_done,
                "episode_reward": ep_final,
                "checkpoint_s3_uri": f"s3://{bucket}/{ckpt_key}",
            }
            if use_federation:
                done_payload["federation_group_id"] = fed_group
                done_payload["federation_size"] = manifest.federation_size

            if use_federation:
                done_key = federation_from_done_key(fed_group, ep, worker_id)
            else:
                done_key = from_worker_done_key(manifest.job_id, ep)
            put_json(bucket, done_key, done_payload)

            # Final artifact for the classic protocol layout
            shutil.copy2(round_save, save_path)

        result_prefix = f"results/{manifest.job_id}"
        checkpoint_s3_uri: Optional[str] = None
        log_s3_uri: Optional[str] = None

        if save_path.exists():
            ckpt_key = f"{result_prefix}/checkpoint_final{ext}"
            upload_file(str(save_path), bucket, ckpt_key)
            checkpoint_s3_uri = f"s3://{bucket}/{ckpt_key}"

        if combined_log.exists():
            log_key = f"{result_prefix}/train.log"
            upload_file(str(combined_log), bucket, log_key)
            log_s3_uri = f"s3://{bucket}/{log_key}"

        total_reward = round(sum(episode_rewards), 4) if episode_rewards else None
        final_reward = round(episode_rewards[-1], 4) if episode_rewards else None

        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="success",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            episodes_completed=len(episode_rewards),
            total_reward=total_reward,
            final_reward=final_reward,
            checkpoint_s3_uri=checkpoint_s3_uri,
            log_s3_uri=log_s3_uri,
        )

    except subprocess.TimeoutExpired:
        logger.error(f"Job {manifest.job_id} timed out during per-episode sync")
        log_uri = _try_upload_train_log(bucket, manifest.job_id, combined_log)
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="timeout",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"Timed out after {manifest.timeout_seconds}s (per-episode sync)",
            log_s3_uri=log_uri,
        )
    except Exception as e:
        logger.exception(f"Job {manifest.job_id} failed (per-episode sync): {e}")
        log_uri = _try_upload_train_log(bucket, manifest.job_id, combined_log)
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="failed",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=str(e),
            log_s3_uri=log_uri,
        )


def _try_upload_train_log(bucket: str, job_id: str, log_path: Path) -> Optional[str]:
    """On failed runs, still upload train.log so S3 has the real error (SimKube, S3, etc.)."""
    if not log_path.exists():
        return None
    try:
        key = f"results/{job_id}/train.log"
        upload_file(str(log_path), bucket, key)
        uri = f"s3://{bucket}/{key}"
        logger.info(f"Uploaded train.log (failed run) → {uri}")
        return uri
    except Exception as ex:
        logger.warning(f"Could not upload train.log: {ex}")
        return None


>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
def run_job(manifest: JobManifest, worker_id: str, bucket: str) -> JobResult:
    """
    Execute one job:
      For training jobs:
        1. Download weights from S3 (if provided)
        2. Run train.py in subprocess with timeout
        3. Upload checkpoint + log to S3
      For experience collection jobs:
        1. Start dist_run in worker mode to generate experiences
        2. Combine transitions and upload them to S3
      4. Return a JobResult (success, failed, or timeout)
    """
    started_at = _now_iso()
    t0 = time.time()

    job_dir = PROJECT_ROOT / ".jobs" / manifest.job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    if manifest.job_type == "experience_collection":
        return _run_experience_collection_job(manifest, worker_id, bucket, job_dir, started_at, t0)

    ext = _ext_for_agent(manifest.agent)
<<<<<<< HEAD
=======
    if manifest.per_episode_s3_sync:
        return _run_training_job_per_episode_sync(
            manifest, worker_id, bucket, job_dir, started_at, t0, ext
        )

>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
=======
        log_uri = _try_upload_train_log(bucket, manifest.job_id, log_path)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="timeout",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=f"Timed out after {manifest.timeout_seconds}s",
<<<<<<< HEAD
=======
            log_s3_uri=log_uri,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        )

    except Exception as e:
        logger.exception(f"Job {manifest.job_id} failed: {e}")
<<<<<<< HEAD
=======
        log_uri = _try_upload_train_log(bucket, manifest.job_id, log_path)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        return JobResult(
            job_id=manifest.job_id,
            worker_id=worker_id,
            status="failed",
            started_at=started_at,
            finished_at=_now_iso(),
            elapsed_seconds=round(time.time() - t0, 1),
            error=str(e),
<<<<<<< HEAD
        )


=======
            log_s3_uri=log_uri,
        )


def _shutdown_host_after_successful_job() -> None:
    """
    Best-effort host shutdown after a successful job (typically with --run-once).
    Requires passwordless sudo or root on the AMI; otherwise this is a no-op aside from a log line.
    """
    logger.warning(
        "shutdown-after-job: requesting system halt (instance may terminate if cloud-init/ASG is configured)"
    )
    for cmd in (
        ["sudo", "-n", "/usr/sbin/shutdown", "-h", "now"],
        ["sudo", "-n", "shutdown", "-h", "now"],
        ["/usr/sbin/shutdown", "-h", "now"],
        ["shutdown", "-h", "now"],
    ):
        try:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return
        except OSError:
            continue
    logger.warning("shutdown-after-job: could not launch shutdown command (no sudo/root?)")


>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
def poll_and_run(
    bucket: str,
    worker_id: str,
    poll_interval: int = 30,
    run_once: bool = False,
<<<<<<< HEAD
=======
    shutdown_after_job: bool = False,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
=======
                if shutdown_after_job and result.status == "success":
                    _shutdown_host_after_successful_job()
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
=======
        "--shutdown-after-job",
        action="store_true",
        help="After a successful job with --run-once, attempt `shutdown -h now` (needs sudo/root on AMI)",
    )
    parser.add_argument(
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
    poll_and_run(args.bucket, worker_id, args.poll_interval, args.run_once)
=======
    poll_and_run(
        args.bucket,
        worker_id,
        args.poll_interval,
        args.run_once,
        shutdown_after_job=args.shutdown_after_job,
    )
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


if __name__ == "__main__":
    main()
