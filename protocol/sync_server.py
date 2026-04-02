#!/usr/bin/env python3
"""
S3 sync server — completes the per-episode loop for jobs with per_episode_s3_sync.

Workers upload checkpoints + done.json under results/<job_id>/sync/from_worker/...
and block before the next episode until weights appear under sync/to_worker/before_ep_XXXX/.

This process polls S3 and, for each done.json, copies the worker checkpoint to the next
episode's expected weights key (identity / pass-through). That unblocks the worker without
using --sync-identity-server on the EC2 side.

For true federated averaging across multiple workers on the *same* job, extend this script
or replace the copy step with aggregation (not implemented here).

Usage:
    export JOBS_BUCKET=your-bucket
    python protocol/sync_server.py --bucket "$JOBS_BUCKET" --poll-interval 15

Run on your laptop, a small EC2, or as a long-lived service. Requires the same S3 IAM
permissions as the worker (GetObject, ListBucket, PutObject for copy_object).
"""

import argparse
import logging
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from protocol.schemas import JobManifest
from protocol.s3_helpers import copy_object, get_json, list_keys, object_exists
from protocol.sync_paths import checkpoint_ext, from_worker_ckpt_key, to_worker_weights_key

logger = logging.getLogger("sync_server")

DONE_KEY_RE = re.compile(
    r"^results/(?P<job_id>[^/]+)/sync/from_worker/after_ep_(?P<ep>\d{4})/done\.json$"
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


def process_bucket_once(bucket: str) -> int:
    """
    Scan the bucket for from_worker/.../done.json markers and copy checkpoints to the
    next to_worker/.../weights path when missing. Returns the number of copy operations.
    """
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


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Poll S3 and copy worker checkpoints to next-episode weight barriers"
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

    logger.info("Sync server watching s3://%s/results/.../sync/", args.bucket)
    while True:
        try:
            n = process_bucket_once(args.bucket)
            if n and args.once:
                logger.info("Applied %s barrier update(s); exiting (--once).", n)
            elif args.once:
                logger.debug("No barrier updates needed; exiting (--once).")
        except Exception:
            logger.exception("Error during S3 scan")
        if args.once:
            break
        time.sleep(max(1, args.poll_interval))


if __name__ == "__main__":
    main()
