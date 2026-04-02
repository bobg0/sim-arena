# Worker Communication Protocol

This document describes how the central server (Task 3) sends jobs to EC2 workers
and how workers return results.  Everything goes through S3 — no message queues needed.

---

## Overview

```
Central server (or operator)          EC2 worker
        │                                  │
        │  1. write manifest.json to S3    │
        │ ────────────────────────────────►│
        │                                  │  2. poll S3, find manifest
        │                                  │  3. download weights (if any)
        │                                  │  4. run train.py
        │                                  │  5. upload checkpoint + log
        │  6. read result.json from S3     │
        │◄──────────────────────────────── │
        │                                  │
        │  (use checkpoint_s3_uri          │
        │   to get new weights)            │
```

---

## S3 Bucket Layout

All objects live in one bucket (default: **`diya-simarena-jobs`**).

```
jobs/
  pending/<job_id>/manifest.json     ← dispatcher writes here
  in_progress/<job_id>/claimed_by    ← worker writes while running (claim marker)

results/
  <job_id>/result.json               ← worker writes when done
  <job_id>/checkpoint_final.pt       ← trained weights (DQN)
  <job_id>/checkpoint_final.json     ← trained weights (greedy/random)
  <job_id>/train.log                 ← full stdout from train.py
```

Traces remain in the **existing** bucket: `s3://diya-simarena-traces/`.

---

## Job Manifest (`manifest.json`)

Written by the dispatcher; read by the worker.

```json
{
  "job_id":           "job_20260325_120000_a1b2c3",
  "trace_s3_uri":     "s3://diya-simarena-traces/demo/trace-mem-slight.msgpack",
  "agent":            "dqn",
  "episodes":         10,
  "steps":            20,
  "duration":         40,
  "namespace":        "default",
  "deploy":           "web",
  "target":           3,
  "weights_s3_uri":   null,
  "timeout_seconds":  3600,
  "created_at":       "2026-03-25T12:00:00Z"
}
```

| Field | Description |
|-------|-------------|
| `job_id` | Unique identifier; also used as the result prefix in S3 |
| `trace_s3_uri` | Full S3 path to the `.msgpack` trace |
| `agent` | `dqn`, `greedy`, or `random` |
| `episodes` / `steps` / `duration` | Passed directly to `train.py` |
| `weights_s3_uri` | S3 URI of a previous checkpoint to resume from — `null` = fresh start |
| `timeout_seconds` | Worker kills `train.py` if it runs longer than this |

---

## Job Result (`result.json`)

Written by the worker after the job finishes (success, failure, or timeout).

```json
{
  "job_id":             "job_20260325_120000_a1b2c3",
  "worker_id":          "i-0abc1234567890def",
  "status":             "success",
  "started_at":         "2026-03-25T12:01:00Z",
  "finished_at":        "2026-03-25T12:31:00Z",
  "elapsed_seconds":    1800.0,
  "episodes_completed": 10,
  "total_reward":       45.23,
  "final_reward":       6.11,
  "error":              null,
  "checkpoint_s3_uri":  "s3://diya-simarena-jobs/results/job_.../checkpoint_final.pt",
  "log_s3_uri":         "s3://diya-simarena-jobs/results/job_.../train.log"
}
```

| Field | Description |
|-------|-------------|
| `status` | `"success"`, `"failed"`, or `"timeout"` |
| `episodes_completed` | Episodes actually run (read from the saved checkpoint) |
| `total_reward` | Sum of all episode rewards |
| `final_reward` | Reward of the last episode |
| `checkpoint_s3_uri` | Where the central server should download new weights from |
| `error` | Error message for non-success statuses; `null` otherwise |

---

## Running the Worker (on EC2)

```bash
# 1. Activate env
source ~/.bashrc
source ~/work/sim-arena/.venv/bin/activate
cd ~/work/sim-arena

# 2. Start the worker (loops until you stop it)
python protocol/worker.py --bucket diya-simarena-jobs

# Optional flags:
#   --worker-id my-worker-1    (default: EC2 instance ID or hostname)
#   --poll-interval 60         (seconds between S3 polls when idle)
#   --run-once                 (process one job then exit — good for testing)
#   --log-level DEBUG
```

The worker polls `jobs/pending/` every `--poll-interval` seconds, claims the first
unclaimed job, runs `train.py`, uploads results, writes `result.json`, then loops.

---

## Submitting a Job (from laptop or central server)

```bash
cd ~/work/sim-arena
source .venv/bin/activate

# Set your jobs bucket once (must match the bucket you created in S3)
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an   # example; use yours

# Fresh start (no prior weights). Put --bucket on the same line as submit/list.
python protocol/dispatch.py submit \
  --bucket "$JOBS_BUCKET" \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 10 --steps 20

# Resume from a previous checkpoint (pass updated weights from central server)
python protocol/dispatch.py submit \
  --bucket "$JOBS_BUCKET" \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 10 \
  --weights s3://$JOBS_BUCKET/results/<prev_job_id>/checkpoint_final.pt
```

### Check job status

```bash
python protocol/dispatch.py list --bucket "$JOBS_BUCKET"
```

Output:

```
Job ID                                        Status       Episodes   Total Reward
-----
job_20260325_120000_a1b2c3                    success            10          45.23
job_20260325_130000_d4e5f6                    pending             -              -
```

---

## Weights Flow (Training Rounds)

```
Round 1:  dispatch submit --trace ...                   (no --weights → fresh start)
          worker runs → writes checkpoint_final.pt

Round 2:  central server aggregates weights (Task 3)
          dispatch submit --trace ... \
            --weights s3://.../results/<round1_job>/checkpoint_final.pt
          worker downloads weights → runs train.py --load ... --transfer
          worker uploads new checkpoint_final.pt

Round N:  repeat
```

The `--transfer` flag (automatically added by the worker when weights are provided)
resets the agent's replay buffer and exploration schedule so learning continues
cleanly from the new weights.

---

## Per-episode S3 sync (optional)

Set `per_episode_s3_sync: true` on the manifest (CLI: `dispatch.py submit --per-episode-sync …`)
when the **central server must refresh weights between every episode** on the same job.

**Worker behaviour**

1. Run `train.py` with `--episodes 1` for each episode (separate subprocess per episode).
2. After episode `e`, upload the checkpoint to  
   `results/<job_id>/sync/from_worker/after_ep_XXXX/checkpoint.{pt|json}`  
   and write `done.json` next to it (`episode_index`, `total_episodes`, `agent`, reward, worker id).
3. Before episode `e+1` (when `e+1 >= 2`), wait until the server object exists:  
   `results/<job_id>/sync/to_worker/before_ep_XXXX/weights.{pt|json}`  
   then download it and pass it to `train.py` as `--load … --transfer`.
4. After the last episode, the worker still writes `checkpoint_final.*`, `train.log`, and `result.json` as in the default layout.

### Included sync server (`sync_server.py`)

The repo ships **`protocol/sync_server.py`**, a small process that **polls S3** and, whenever it sees
`from_worker/after_ep_XXXX/done.json`, **copies** the matching worker checkpoint to
`to_worker/before_ep_{XXXX+1}/weights.*` if that key does not exist yet. That is an **identity
(pass-through)** barrier: it completes the loop so workers do not need `--sync-identity-server`.

Run it anywhere with bucket credentials (laptop, tiny EC2, systemd service):

```bash
cd ~/work/sim-arena && source .venv/bin/activate
export JOBS_BUCKET=your-jobs-bucket
python protocol/sync_server.py --bucket "$JOBS_BUCKET" --poll-interval 15
# one-shot (e.g. cron):
python protocol/sync_server.py --bucket "$JOBS_BUCKET" --once
```

**Replacing pass-through with real aggregation:** swap the `copy_object` step in `sync_server.py`
for your own logic (e.g. FedAvg over several checkpoints), or run a separate service that writes
the same `to_worker/…` keys. The worker only cares that the object appears.

**Testing without `sync_server.py`:** `dispatch.py submit --per-episode-sync --sync-identity-server …`
still makes the worker copy the checkpoint into the next `to_worker/…` key on the instance itself.

**Timeouts:** `sync_server_weights_timeout_seconds` on the manifest caps how long the worker waits at each barrier. Each `train.py` subprocess is still limited by `timeout_seconds` on the manifest.

**Parallel EC2 instances:** unchanged — each instance claims a different `job_id` under `jobs/pending/`. Submit one manifest per instance (or run `ops/ec2_workers.py` / your launcher) so many workers pick up different jobs in parallel.

**Stopping the instance after N episodes:** the worker does not count episodes across jobs. After exactly one manifest with `episodes: N` finishes, use  
`python protocol/worker.py --bucket … --run-once --shutdown-after-job`  
so the process exits and the AMI attempts `shutdown -h now` (needs passwordless `sudo` or root). Pair with an ASG lifecycle rule or `InstanceInitiatedShutdownBehavior` / spot interruption as appropriate.

---

## Failure Handling

| Scenario | Worker behaviour | result.json `status` |
|----------|-----------------|----------------------|
| `train.py` exits non-zero | Log uploaded if available; no checkpoint | `"failed"` |
| Job exceeds `timeout_seconds` | `subprocess.run` raises `TimeoutExpired`; process killed | `"timeout"` |
| Weights download fails | Exception caught; job marked failed immediately | `"failed"` |
| Two workers claim same job | Both may run it; central server deduplicates by `job_id` | whichever writes last wins |

---

## Environment Variables

The worker inherits these from the shell (same as running `train.py` directly):

| Variable | Required | Notes |
|----------|----------|-------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Yes | For S3 reads/writes |
| `AWS_DEFAULT_REGION` | Yes | Default: `us-east-2` |
| `SIM_ARENA_DRIVER_TIMEOUT` | Recommended | Set to `150` on EC2 |
| `SIM_ARENA_DEPLOY_TIMEOUT` | Recommended | Set to `90` on EC2 |
| `SIM_ARENA_NODE_DATA_DIR` | Yes | `/var/kind/cluster` on EC2 |
| `JOBS_BUCKET` | Optional | Overrides `--bucket` default |

---

## Code Layout

```
protocol/
  schemas.py      — JobManifest and JobResult dataclasses
  s3_helpers.py   — thin boto3 wrappers (upload, download, list, put/get JSON)
  sync_paths.py   — S3 key helpers for per-episode sync
  sync_server.py  — polls S3 and publishes next-episode weights (identity copy by default)
  worker.py       — EC2 worker polling loop
  dispatch.py     — submit jobs and check status from a laptop or central server

tests/
  test_protocol.py   — worker/dispatch/schema tests (mocked)
  test_sync_server.py — sync server and path tests (mocked)
```
