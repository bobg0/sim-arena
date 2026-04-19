# AWS Distributed Training

Sim-Arena supports distributed reinforcement learning training across multiple EC2 workers using S3 for coordination and federated averaging.

## Overview

Instead of training on a single machine, distribute episodes across multiple EC2 instances. Workers upload checkpoints to S3, and a sync server performs federated averaging to combine model updates.

## Architecture

```
┌─────────────┐    ┌─────────────┐
│   Worker 1  │    │   Worker 2  │
│             │    │             │
│ train.py ──►│    │ train.py ──►│
│ episode 1   │    │ episode 1   │
└──────┬──────┘    └──────┬──────┘
       │                  │
       └─────────┬────────┘
                 │
          ┌──────▼──────┐
          │     S3      │
          │             │
          │ checkpoints │
          └──────┬──────┘
                 │
          ┌──────▼──────┐
          │ Sync Server │
          │             │
          │ FedAvg ────►│
          │ global_wts  │
          └─────────────┘
```

## Quick Start

### 1. Launch EC2 Workers

Use the prebuilt AMI `simkube-simarena-s3-ready-2026-03-08` in us-east-2.

Launch 2+ instances with:
- Instance type: t3.medium or larger
- Security group: Allow SSH and any needed ports

### 2. Configure S3

Create an S3 bucket for job coordination:

```bash
aws s3 mb s3://your-bucket-name --region us-east-2
```

### 3. Submit Jobs

From your local machine:

```bash
export JOBS_BUCKET=your-bucket-name
GROUP="training-$(date +%Y%m%d-%H%M)"

# Submit job for each worker
python protocol/dispatch.py submit \
  --bucket "$JOBS_BUCKET" \
  --trace s3://traces/demo/trace-mem-slight.msgpack \
  --agent dqn --episodes 2 --steps 3 --duration 40 \
  --federation-group "$GROUP" --federation-size 2
```

### 4. Start Sync Server

```bash
python protocol/sync_server.py --bucket "$JOBS_BUCKET" --poll-interval 10
```

### 5. Run Workers

On each EC2 instance:

```bash
# SSH in and run
python protocol/worker.py --bucket "$JOBS_BUCKET" --run-once
```

## Detailed Setup

See [EC2 Multi-Worker Runbook](EC2_MULTI_WORKER_RUNBOOK.md) for complete instructions.

## Key Components

### dispatch.py
CLI tool to submit training jobs to S3. Creates job manifests for workers.

### worker.py
Runs on EC2 instances. Polls S3 for jobs, runs `train.py`, uploads results.

### sync_server.py
Coordinates federated averaging. Waits for all workers in a group to finish an episode, then averages weights.

### Federated Averaging
Combines model updates from multiple workers using weighted averaging based on episode data.

## Configuration

### Environment Variables

On workers:
- `AWS_ACCESS_KEY_ID`
- `AWS_SECRET_ACCESS_KEY`
- `AWS_DEFAULT_REGION=us-east-2`
- `JOBS_BUCKET`
- `SIM_ARENA_DRIVER_TIMEOUT=150`
- `SIM_ARENA_DEPLOY_TIMEOUT=90`
- `PYTHONPATH=/home/ubuntu/work/sim-arena`

### Job Parameters

- `--federation-group`: Group ID for averaging
- `--federation-size`: Number of workers in group
- `--episodes`: Episodes per worker
- `--steps`: Max steps per episode

## Monitoring

- Check S3 bucket for uploaded checkpoints
- View worker logs in `checkpoints/` on each EC2
- Sync server prints averaging progress

## Scaling

- Start with 2 workers for testing
- Scale to 4-8 for production training
- Use larger instance types for complex models

## Troubleshooting

- Ensure AWS credentials are set on workers
- Check `kubectl get nodes` on each worker
- Verify S3 permissions for bucket access
- Use `--log-level DEBUG` for detailed logs

## Costs

- EC2 instances: ~$0.10/hour for t3.medium
- S3 storage: Minimal for checkpoints
- Monitor usage to control costs