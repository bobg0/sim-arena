# Worker Communication Protocol

This document describes how jobs are dispatched to EC2 workers and how workers return results. Everything goes through S3 — no message queues needed.

---

## Overview

```
Operator (laptop or server)           EC2 worker
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

For federated runs, a **`sync_server.py`** process (running on any machine with S3 access) sits between workers and handles weight aggregation:

```
Worker 1 ──► upload ep1 checkpoint ──► S3
Worker 2 ──► upload ep1 checkpoint ──► S3
                                         │
                                   sync_server.py
                                   (FedAvg → global_weights.pt)
                                         │
Worker 1 ◄── download global_weights ───┘
Worker 2 ◄── download global_weights ───┘
  (both continue with ep2 from shared averaged policy)
```

---

## S3 Bucket Layout

All objects live in one bucket (e.g. **`diya-simarena-jobs-664926621123-us-east-2-an`**).

```
jobs/
  pending/<job_id>/manifest.json      ← dispatcher writes here
  in_progress/<job_id>/claimed_by     ← worker writes while running (claim marker)

results/
  <job_id>/result.json                ← worker writes when done
  <job_id>/checkpoint_final.pt        ← trained weights (DQN)
  <job_id>/checkpoint_final.json      ← trained weights (greedy/random)
  <job_id>/train.log                  ← full stdout from train.py

  _federation/<group_id>/
    from_worker/after_ep_XXXX/<worker_id>/checkpoint.pt   ← per-worker upload
    from_worker/after_ep_XXXX/<worker_id>/done.json
    to_worker/before_ep_XXXX/global_weights.pt            ← FedAvg output
```

Traces remain in the separate bucket: `s3://diya-simarena-traces/`.

---

## Job Manifest (`manifest.json`)

Written by the dispatcher; read by the worker.

```json
{
  "job_id":           "job_20260325_120000_a1b2c3",
  "trace_s3_uri":     "s3://diya-simarena-traces/demo/trace-mem-slight.msgpack",
  "agent":            "dqn",
  "episodes":         2,
  "steps":            3,
  "duration":         40,
  "namespace":        "default",
  "deploy":           "web",
  "target":           3,
  "weights_s3_uri":   null,
  "timeout_seconds":  7200,
  "per_episode_s3_sync": true,
  "federation_group_id": "fedrun-20260407-1656",
  "federation_size":  2,
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
| `timeout_seconds` | Worker kills `train.py` if it runs longer than this (default 3600; use 7200+ for longer runs) |
| `per_episode_s3_sync` | When `true`, worker runs one episode at a time and synchronises weights via S3 between each |
| `federation_group_id` | Non-empty means federated run; all jobs with same ID share one global model |
| `federation_size` | Number of workers that must finish an episode before FedAvg runs |

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
  "episodes_completed": 2,
  "total_reward":       -2.70,
  "final_reward":       -1.35,
  "error":              null,
  "checkpoint_s3_uri":  "s3://diya-simarena-jobs-.../results/job_.../checkpoint_final.pt",
  "log_s3_uri":         "s3://diya-simarena-jobs-.../results/job_.../train.log"
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
# 0. Health check — do this EVERY session before starting the worker
kubectl get pods -A | grep kwok          # must be Running, not CrashLoopBackOff
kubectl get nodes                         # all needed nodes must be Ready
kubectl delete simulations.simkube.io --all -n default 2>/dev/null || true
pkill -f "train.py" 2>/dev/null || true

# 1. Activate env
source ~/work/sim-arena/.venv/bin/activate
cd ~/work/sim-arena

# 2. Export env vars
export AWS_ACCESS_KEY_ID=<your_key>
export AWS_SECRET_ACCESS_KEY=<your_secret>
export AWS_DEFAULT_REGION=us-east-2
export SIM_ARENA_DRIVER_TIMEOUT=150
export SIM_ARENA_DEPLOY_TIMEOUT=90
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
export PYTHONPATH=/home/ubuntu/work/sim-arena
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an

# 3. Refresh K8s secret
kubectl create secret generic simkube -n simkube \
  --from-literal=AWS_ACCESS_KEY_ID=$AWS_ACCESS_KEY_ID \
  --from-literal=AWS_SECRET_ACCESS_KEY=$AWS_SECRET_ACCESS_KEY \
  --from-literal=AWS_DEFAULT_REGION=us-east-2 \
  --dry-run=client -o yaml | kubectl apply -f -

# 4. Run worker (process one job then exit)
python protocol/worker.py --bucket "$JOBS_BUCKET" --run-once --log-level INFO

# Or run continuously (loops and polls every 30s when idle):
python protocol/worker.py --bucket "$JOBS_BUCKET" --log-level INFO
```

The worker polls `jobs/pending/` every `--poll-interval` seconds, claims the first unclaimed job, runs `train.py`, uploads results, writes `result.json`, then loops.

**Why the health check matters:** If KWOK is crashing or nodes are NotReady, `train.py` will hang waiting for pods that never get scheduled, and the job will timeout after `timeout_seconds`. Ghost `simulations.simkube.io` CRDs left over from killed/timed-out runs have the same effect — delete them first.

---

## Submitting a Job (from laptop)

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an

# Single worker, fresh start
python protocol/dispatch.py submit \
  --bucket "$JOBS_BUCKET" \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 2 --steps 3 --duration 40 --timeout 7200

# Federated run (submit once per worker, same GROUP)
GROUP="fedrun-$(date +%Y%m%d-%H%M)"
python protocol/dispatch.py submit \
  --bucket "$JOBS_BUCKET" \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 2 --steps 3 --duration 40 --timeout 7200 \
  --federation-group "$GROUP" --federation-size 2
# run the above command TWICE (once per worker)
```

### Check job status

```bash
python protocol/dispatch.py list --bucket "$JOBS_BUCKET"
```

Output:

```
Job ID                                        Status       Episodes   Total Reward
-------------------------------------------------------------------------------------
job_20260407_235626_f1d114                    success             2          -2.70
job_20260407_235626_f922f1                    success             2          -2.70
job_20260409_051223_5263ff                    pending             -              -
```

### Cancel / remove a stale job

```bash
# Remove from pending so workers don't pick it up
aws s3 rm "s3://$JOBS_BUCKET/jobs/pending/JOB_ID/manifest.json"
# Remove claim marker if one exists
aws s3 rm "s3://$JOBS_BUCKET/jobs/in_progress/JOB_ID/claimed_by" 2>/dev/null || true
```

---

## Per-episode S3 Sync

Set `per_episode_s3_sync: true` on the manifest (CLI: `dispatch.py submit --per-episode-sync …`) when weights must be refreshed between every episode on the same job.

**Worker behaviour:**

1. Run `train.py` with `--episodes 1` for each episode (separate subprocess per episode).
2. After episode `e`, upload the checkpoint to
   `results/<job_id>/sync/from_worker/after_ep_XXXX/checkpoint.{pt|json}`
   and write `done.json` next to it.
3. Before episode `e+1`, wait until the server object exists:
   `results/<job_id>/sync/to_worker/before_ep_XXXX/weights.{pt|json}`
   then download it and pass it to `train.py` as `--load … --transfer`.
4. After the last episode, the worker still writes `checkpoint_final.*`, `train.log`, and `result.json`.

---

## Federated Learning (FedAvg, DQN only)

### How it works

Use the same `--federation-group` on every manifest and set `--federation-size` to the number of workers that must finish an episode before the round advances.

1. **Dispatch:** submit `federation_size` jobs all with the same `--federation-group` and `--federation-size`.
2. **Workers** run episode 1 independently, upload checkpoints under `results/_federation/<group>/from_worker/after_ep_0001/<worker_id>/`.
3. **`sync_server.py`** waits until `federation_size` distinct `worker_id`s have uploaded for that episode, then runs **FedAvg** (mean of `q_net_state_dict` and `target_net_state_dict`), and writes one file for everyone: `results/_federation/<group>/to_worker/before_ep_0002/global_weights.pt`.
4. **Workers** download that same object and continue episode 2 from the shared averaged policy.

### Running the sync server

Run this anywhere with S3 credentials (laptop, small EC2, etc.) and keep it running for the duration of the federated job:

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an
python protocol/sync_server.py --bucket "$JOBS_BUCKET" --poll-interval 10 --log-level INFO
```

**Order of operations:** submit jobs → start `sync_server` → start all workers. Workers block at each episode barrier until `sync_server` publishes `global_weights.pt`.

### Important notes

- Submit **exactly `federation_size` jobs** with the same group ID; workers block until the barrier fills.
- **Agent must be `dqn`** for FedAvg (`.pt` checkpoints). Greedy/random agents use identity copy.
- **Do not** use `--sync-identity-server` with `--federation-group` — use `sync_server.py` for FedAvg.
- `sync_server_weights_timeout_seconds` (default 7200) caps how long each worker waits at a barrier.
- `timeout_seconds` on the manifest caps how long each individual `train.py` subprocess runs.

---

## Weights Flow (Training Rounds without Federation)

```
Round 1:  dispatch submit --trace ...                   (no --weights → fresh start)
          worker runs → writes checkpoint_final.pt

Round 2:  dispatch submit --trace ... \
            --weights s3://.../results/<round1_job>/checkpoint_final.pt
          worker downloads weights → runs train.py --load ... --transfer
          worker uploads new checkpoint_final.pt

Round N:  repeat
```

The `--transfer` flag (automatically added by the worker when weights are provided) resets the agent's replay buffer and exploration schedule so learning continues cleanly from the new weights.

---

## Failure Handling

| Scenario | Worker behaviour | result.json `status` |
|----------|-----------------|----------------------|
| `train.py` exits non-zero | Log uploaded if available; no checkpoint | `"failed"` |
| Job exceeds `timeout_seconds` | `subprocess.run` raises `TimeoutExpired`; process killed | `"timeout"` |
| Weights download fails | Exception caught; job marked failed immediately | `"failed"` |
| Two workers claim same job | Both may run it; deduplication happens via `claimed_by` check | first writer wins |
| KWOK CrashLoopBackOff | train.py hangs (pods never schedule) → timeout | `"timeout"` |
| Ghost simulations in namespace | train.py hangs immediately → timeout | `"timeout"` |

---

## Environment Variables

The worker inherits these from the shell (same as running `train.py` directly):

| Variable | Required | Notes |
|----------|----------|-------|
| `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY` | Yes | For S3 reads/writes |
| `AWS_DEFAULT_REGION` | Yes | Use `us-east-2` |
| `SIM_ARENA_DRIVER_TIMEOUT` | Recommended | Set to `150` on EC2 |
| `SIM_ARENA_DEPLOY_TIMEOUT` | Recommended | Set to `90` on EC2 |
| `SIM_ARENA_NODE_DATA_DIR` | Yes | `/var/kind/cluster` on EC2 |
| `PYTHONPATH` | Yes | `/home/ubuntu/work/sim-arena` on EC2 |
| `JOBS_BUCKET` | Optional | Overrides `--bucket` default |

---

## Code Layout

```
protocol/
  schemas.py       — JobManifest and JobResult dataclasses
  s3_helpers.py    — thin boto3 wrappers (upload, download, list, put/get JSON)
  sync_paths.py    — canonical S3 key helpers for per-episode sync and federation
  sync_server.py   — polls S3: identity barriers + FedAvg for federation groups
  federated_avg.py — mean of DQN q_net / target_net checkpoints
  worker.py        — EC2 worker polling loop
  dispatch.py      — submit jobs and check status from a laptop or central server

tests/
  test_protocol.py      — worker/dispatch/schema tests (mocked, no AWS needed)
  test_sync_server.py   — sync server and path tests (mocked)
  test_federated_avg.py — FedAvg tensor math
```
