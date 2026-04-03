#!/usr/bin/env python3
"""
S3 sync server — completes per-episode barriers and federated (FedAvg) global weights.

1) Single-worker jobs (per_episode_s3_sync, no federation_group_id):
   copies each job's checkpoint to that job's next to_worker/weights key.

2) Federated jobs (same federation_group_id, federation_size > 1, agent=dqn):
   after each episode, waits until `federation_size` workers have uploaded under
   results/_federation/<group>/from_worker/..., then averages q_net / target_net (FedAvg),
   uploads results/_federation/<group>/to_worker/before_ep_XXXX/global_weights.pt
   for all workers to download before the next episode.

Usage:
    export JOBS_BUCKET=your-bucket
    python protocol/sync_server.py --bucket "$JOBS_BUCKET" --poll-interval 15
"""

import argparse
import logging
import os
import re
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, Optional, Set, Tuple

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from protocol.schemas import JobManifest
from protocol.s3_helpers import (
    copy_object,
    download_file,
    get_json,
    list_keys,
    object_exists,
    upload_file,
)
from protocol.sync_paths import (
    checkpoint_ext,
    federation_from_ckpt_key,
    federation_global_weights_key,
    from_worker_ckpt_key,
    to_worker_weights_key,
)

logger = logging.getLogger("sync_server")

DONE_KEY_RE = re.compile(
    r"^results/(?P<job_id>[^/]+)/sync/from_worker/after_ep_(?P<ep>\d{4})/done\.json$"
)

FED_DONE_RE = re.compile(
    r"^results/_federation/(?P<gid>[^/]+)/from_worker/after_ep_(?P<ep>\d{4})/"
    r"(?P<wid>[^/]+)/done\.json$"
)


def _total_episodes_from_manifest(bucket: str, job_id: str) -> Optional[int]:
    key = f"jobs/pending/{job_id}/manifest.json"
    if not object_exists(bucket, key):
        return None
    try:
        return JobManifest.from_dict(get_json(bucket, key)).episodes
    except Exception as e:
        logger.warning("Could not read manifest for %s: %s", job_id, e)
        return None


def _process_single_worker_sync(bucket: str) -> int:
    actions = 0
    keys = list_keys(bucket, "results/")
    for key in keys:
        m = DONE_KEY_RE.match(key)
        if not m:
            continue
        job_id = m.group("job_id")
        finished_ep = int(m.group("ep"))
        try:
            done = get_json(bucket, key)
        except Exception as e:
            logger.warning("Skipping %s: %s", key, e)
            continue

        if done.get("federation_group_id"):
            continue

        total_episodes = done.get("total_episodes")
        if total_episodes is None:
            total_episodes = _total_episodes_from_manifest(bucket, job_id)
        if total_episodes is None:
            logger.warning("Skipping %s: cannot determine total_episodes", key)
            continue

        if finished_ep >= total_episodes:
            continue

        agent = done.get("agent") or "dqn"
        ext = checkpoint_ext(agent)
        src = from_worker_ckpt_key(job_id, finished_ep, ext)
        dst = to_worker_weights_key(job_id, finished_ep + 1, ext)

        if not object_exists(bucket, src):
            logger.debug("Source checkpoint not yet present: %s", src)
            continue
        if object_exists(bucket, dst):
            continue

        copy_object(bucket, src, dst)
        logger.info(
            "Published weights for job %s before episode %s → s3://%s/%s",
            job_id,
            finished_ep + 1,
            bucket,
            dst,
        )
        actions += 1
    return actions


def _process_federation_sync(bucket: str) -> int:
    try:
        import torch
    except ImportError:
        logger.warning("torch not installed; skipping federation FedAvg step")
        return 0

    from protocol.federated_avg import fedavg_dqn_checkpoints

    actions = 0
    keys = list_keys(bucket, "results/_federation/")
    ready: Dict[Tuple[str, int], Set[str]] = defaultdict(set)
    size_for: Dict[Tuple[str, int], int] = {}
    agent_for: Dict[Tuple[str, int], str] = {}
    total_ep_for: Dict[Tuple[str, int], int] = {}

    for key in keys:
        m = FED_DONE_RE.match(key)
        if not m:
            continue
        gid = m.group("gid")
        ep = int(m.group("ep"))
        wid = m.group("wid")
        try:
            done = get_json(bucket, key)
        except Exception as e:
            logger.warning("Skipping %s: %s", key, e)
            continue

        agent = done.get("agent") or "dqn"
        if agent != "dqn":
            logger.warning("Federation FedAvg supports dqn only; skipping %s", key)
            continue

        fs = int(done.get("federation_size", 1))
        if fs < 1:
            continue
        total_ep = int(done.get("total_episodes", 0))
        if total_ep < 1:
            continue

        ext = checkpoint_ext(agent)
        ck = federation_from_ckpt_key(gid, ep, wid, ext)
        if not object_exists(bucket, ck):
            continue

        sig = (gid, ep)
        ready[sig].add(wid)
        size_for[sig] = fs
        agent_for[sig] = agent
        total_ep_for[sig] = total_ep

    for sig, wids in ready.items():
        gid, finished_ep = sig
        fs = size_for[sig]
        agent = agent_for[sig]
        total_episodes = total_ep_for[sig]
        if len(wids) < fs:
            logger.debug(
                "Federation %s ep %s: %s/%s workers ready",
                gid,
                finished_ep,
                len(wids),
                fs,
            )
            continue

        next_ep = finished_ep + 1
        if next_ep > total_episodes:
            continue

        ext = checkpoint_ext(agent)
        dst = federation_global_weights_key(gid, next_ep, ext)
        if object_exists(bucket, dst):
            continue

        participants = sorted(wids)[:fs]
        try:
            with tempfile.TemporaryDirectory() as td:
                tdir = Path(td)
                local_paths = []
                for wid in participants:
                    ck = federation_from_ckpt_key(gid, finished_ep, wid, ext)
                    lp = tdir / f"{wid}.pt"
                    download_file(bucket, ck, str(lp))
                    local_paths.append(lp)

                merged = fedavg_dqn_checkpoints(local_paths)
                out_path = tdir / "global_weights.pt"
                torch.save(merged, str(out_path))
                upload_file(str(out_path), bucket, dst)

            logger.info(
                "FedAvg published for group %s before episode %s (%s workers) → s3://%s/%s",
                gid,
                next_ep,
                len(participants),
                bucket,
                dst,
            )
            actions += 1
        except Exception:
            logger.exception(
                "FedAvg failed for group %s after episode %s", gid, finished_ep
            )

    return actions


def process_bucket_once(bucket: str) -> int:
    return _process_single_worker_sync(bucket) + _process_federation_sync(bucket)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="S3 sync: per-job barriers + federated FedAvg between episodes"
    )
    parser.add_argument(
        "--bucket",
        default=os.getenv("JOBS_BUCKET", "diya-simarena-jobs"),
        help="Jobs/results bucket (default: JOBS_BUCKET env or diya-simarena-jobs)",
    )
    parser.add_argument(
        "--poll-interval",
        type=int,
        default=15,
        help="Seconds to sleep between full bucket scans (default: 15)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Run a single scan then exit (useful with cron or systemd oneshot)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s [sync_server] %(message)s",
        stream=sys.stdout,
    )

    logger.info(
        "Sync server: single-worker sync + federation under s3://%s/results/",
        args.bucket,
    )
    while True:
        try:
            n = process_bucket_once(args.bucket)
            if n and args.once:
                logger.info("Applied %s update(s); exiting (--once).", n)
            elif args.once:
                logger.debug("No updates needed; exiting (--once).")
        except Exception:
            logger.exception("Error during S3 scan")
        if args.once:
            break
        time.sleep(max(1, args.poll_interval))


if __name__ == "__main__":
    main()
