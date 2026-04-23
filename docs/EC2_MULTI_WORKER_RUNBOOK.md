# ™™

This is the operational playbook for running distributed/federated training across multiple EC2 workers and collecting evidence from each worker run.

Automation entrypoint: [ops/ec2_workers.py](../ops/ec2_workers.py)

---

## 1) Prerequisites (local operator machine)

Required:

- Repo cloned at `~/clinic_ACRL/sim-arena`
- Virtualenv activated (`source .venv/bin/activate`)
- AWS credentials configured (`AWS_PROFILE` or env vars)
- SSH key PEM available locally (example: `~/clinic_ACRL/diya_simkube_key.pem`)
- `aws`, `kubectl`, `python` available in shell

Known-good defaults in this project:

- Region: `us-east-2`
- AMI: `ami-08d19a1b7f569b848`
- Trace bucket: `diya-simarena-traces`
- Jobs/results bucket: `diya-simarena-jobs-664926621123-us-east-2-an`
- Demo trace: `s3://diya-simarena-traces/demo/trace-mem-slight.msgpack`

---

## 2) AWS values you must confirm before launch

1. EC2 key pair name (example: `diya_simkube_key`)
2. Security group ID (`sg-...`) with inbound SSH allowed from your machine
3. Subnet ID (`subnet-...`) with public IP behavior you expect
4. Instance count and type (`c6a.xlarge` has been used in recent runs)

---

## 3) Launch workers

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate

python ops/ec2_workers.py launch \
  --count 2 \
  --region us-east-2 \
  --instance-type c6a.xlarge \
  --key-name diya_simkube_key \
  --ssh-key-path ~/clinic_ACRL/diya_simkube_key.pem \
  --security-group-id sg-REPLACE_ME \
  --subnet-id subnet-REPLACE_ME
```


use ```
aws ec2 describe-subnets --region us-east-2 --output table
```
# USE THE RIGHT REGION in your AWS console!!! 

minor note on pem file permissions:
```
chmod 400 /home/bogao/.ssh/bob-s3-test-key.pem
```

to find the corresponding subnet and securityu group
<!-- python ops/ec2_workers.py launch \
  --count 2 \
  --region us-east-2 \
  --instance-type c6a.xlarge \
  --key-name diya_simkube_key \
  --ssh-key-path /home/bogao/.ssh/simkube-test-bob.pem\
  --security-group-id sg-REPLACE_ME \
  --subnet-id subnet-REPLACE_ME -->

What this gives you:

- Tagged worker instances
- `runs/ec2_workers/<run-id>.json` inventory file with instance IDs and IPs
- Optional secret bootstrap for `simkube`

---

## 4) Mandatory worker preflight checks (run on every worker before jobs)

Use this before starting `protocol/worker.py`. It prevents the exact stuck-run behavior seen previously.

```bash
# On worker (SSH session)
cd ~/work/sim-arena
source .venv/bin/activate

echo "=== KWOK and node health ==="
kubectl get pods -A | egrep "kwok|controller|simkube" || true
kubectl get nodes -o wide

echo "=== Clear stale sims/processes ==="
pkill -f "train.py.*--ns default" || true
kubectl delete simulations.simkube.io --all -n default || true
kubectl delete simulations.simkube.io --all -n virtual-default || true

echo "=== Sanity observation ==="
python runner/one_step.py \
  --trace demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent greedy \
  --reward shaped \
  --log-level INFO
```

Healthy expectation:

- `kwok-controller` is not CrashLooping
- `kubectl get nodes` shows Ready
- one-step finishes and prints an observation

---

## 5) Start worker daemons (each EC2)

```bash
cd ~/work/sim-arena
source .venv/bin/activate
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an
export AWS_REGION=us-east-2

python protocol/worker.py
```

Keep one terminal per worker so logs are visible.

---

## 6) Start sync server (controller machine)

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
export JOBS_BUCKET=diya-simarena-jobs-664926621123-us-east-2-an
export AWS_REGION=us-east-2

python protocol/sync_server.py
```

For federated runs, this process must remain alive during the full run.

---

## 7) Dispatch multi-worker run

Dispatch two jobs with the same federation group and `per_episode_s3_sync=true`.

Checklist for manifests:

- `federation_group_id` same for all workers in the batch
- `federation_size` equals worker count
- `episodes >= 2` if you want to prove round-2 used server/global weights
- `timeout_seconds` high enough for your slowest cluster cycle

---

## 8) Live monitoring during run

### 8.1 S3 sync paths

Check whether each episode is progressing through barriers:

```bash
aws s3 ls s3://$JOBS_BUCKET/results/_federation/<group-id>/ --recursive
```

Look for:

- `from_worker/after_ep_0001/<worker-id>/checkpoint.pt`
- `to_worker/before_ep_0002/global_weights.pt`

### 8.2 Worker-level logs and artifacts

```bash
python protocol/inspect_run.py --list
python protocol/inspect_run.py <job_id> --log
python protocol/inspect_run.py <job_id> --ckpt
```

For runs after the `steps.jsonl` upload change:

```bash
python protocol/inspect_run.py <job_id> --steps
```

---

## 9) How to prove parallelization and weight handoff

Use these three evidence types:

1. **Concurrency proof**  
   Two `job_id`s with overlapping timestamps in logs.

2. **Federation barrier proof**  
   S3 keys under `results/_federation/<group-id>/...` show both workers uploading `after_ep_0001` before a single `global_weights` is emitted for `before_ep_0002`.

3. **Round-2 weight-load proof**  
   Worker logs contain:
   `Loading agent weights from .../server_weights_ep_0002.pt`

---

## 10) Failure patterns and quick actions

- **All observations stuck (`ready=0, pending=3, total=3`) for every step**  
  SimKube is not applying actions effectively. Check KWOK/controller health first.

- **Repeated `Driver pod didn't enter Running state within 150s`**  
  Cluster is degraded or delayed; do not trust training quality until fixed.

- **`Timed out after 3600s` with `episodes_completed=0`**  
  Job never completed episode 1. Increase timeout only after fixing cluster health.

- **Action blocked by safeguards (memory > 32Gi)**  
  Expected if agent proposes out-of-bounds action. Not fatal by itself.

---

## 11) Cleanup

Terminate from inventory:

```bash
python ops/ec2_workers.py terminate --inventory-file runs/ec2_workers/<run-id>.json --yes
```

Stop (debugging only):

```bash
python ops/ec2_workers.py stop --inventory-file runs/ec2_workers/<run-id>.json
```

Terminate is preferred for cost control.

---

## 12) Related docs

- [docs/WORKER_PROTOCOL.md](WORKER_PROTOCOL.md)
- [docs/EC2_SETUP_FROM_SCRATCH.md](EC2_SETUP_FROM_SCRATCH.md)
- [TRAINING_SERVER_README.md](../TRAINING_SERVER_README.md)
