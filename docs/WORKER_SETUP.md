# SimArena Worker Setup

## EC2 Instance

| Field | Value |
|---|---|
| AMI name | `simkube-simarena-s3-ready-2026-03-08` |
| AMI ID | `ami-08d19a1b7f569b848` |
| Region | `us-east-2` (US East — Ohio) |
| Instance type | `t3.large` |
| Key pair | `diya_simkube_key.pem` |
| Security group | `default` |

## AWS Resources

| Resource | Value |
|---|---|
| S3 bucket | `diya-simarena-traces` |
| Bucket region | `us-east-2` |
| IAM user | `simkube-s3-user` |

## Repo

```
https://github.com/bobg0/sim-arena
```

## SSH into the instance

```bash
ssh -i diya_simkube_key.pem ubuntu@<EC2_PUBLIC_IP>
```

## Environment (pre-baked into AMI)

These are already set in `~/.bashrc` — no manual exports needed on a fresh instance:

```bash
AWS_ACCESS_KEY_ID=...          # simkube-s3-user credentials
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=us-east-2
SIM_ARENA_DRIVER_TIMEOUT=150
SIM_ARENA_DEPLOY_TIMEOUT=90
SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
PYTHONPATH=/home/ubuntu/work/sim-arena
```

The `simkube` Kubernetes secret in the cluster also has `AWS_DEFAULT_REGION=us-east-2`
so the SimKube driver pod can download traces from S3.

## First-time setup on a new instance

```bash
cd ~/work/sim-arena
git pull
source .venv/bin/activate
```

## Run a single simulation step

```bash
cd ~/work/sim-arena
source .venv/bin/activate
export PYTHONPATH=.

python runner/one_step.py \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent bump_cpu \
  --log-level INFO
```

Expected output (working):
```
INFO Deployment 'web' found (6.2s)
INFO Observation: {'ready': 0, 'pending': 3, 'total': 3}
INFO Step Summary: action=bump_cpu_small, reward=..., changed=True
```

## Run a full training session

```bash
python runner/train.py \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --agent dqn \
  --episodes 10 \
  --steps 5 \
  --duration 40 \
  --reward cost_aware_v2
```

## S3 trace files

| Path | Description |
|---|---|
| `s3://diya-simarena-traces/demo/trace-mem-slight.msgpack` | Valid trace — memory-slight workload, `default` namespace, `web` deployment |
| `s3://diya-simarena-traces/traces/trace-*.msgpack` | Numbered traces — **invalid CPU units**, do not use for training |

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Deployment 'web' not found within 90s` | Driver pod failing | Check `kubectl logs -n simkube -l job-name=sk-diag-*` |
| `error: unexpected argument '--virtual-ns-prefix'` | Driver image version mismatch | Set `SIM_ARENA_DRIVER_IMAGE=quay.io/appliedcomputing/sk-driver:v2.4.1` |
| `Received redirect without LOCATION` | Wrong S3 region in cluster secret | Run: `kubectl create secret generic simkube -n simkube --from-literal=AWS_DEFAULT_REGION=us-east-2 --dry-run=client -o yaml \| kubectl apply -f -` |
| `FileNotFoundError: 's3://...'` | Old code trying to copy S3 path locally | `git pull` to get the S3 direct-pass fix |
