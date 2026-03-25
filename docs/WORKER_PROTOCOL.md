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

# Fresh start (no prior weights)
python protocol/dispatch.py submit \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 10 --steps 20

# Resume from a previous checkpoint (pass updated weights from central server)
python protocol/dispatch.py submit \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 10 \
  --weights s3://diya-simarena-jobs/results/<prev_job_id>/checkpoint_final.pt
```

### Check job status

```bash
python protocol/dispatch.py list
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
  schemas.py     — JobManifest and JobResult dataclasses
  s3_helpers.py  — thin boto3 wrappers (upload, download, list, put/get JSON)
  worker.py      — EC2 worker polling loop
  dispatch.py    — submit jobs and check status from a laptop or central server

tests/
  test_protocol.py — 22 unit tests (no AWS credentials required)
```
