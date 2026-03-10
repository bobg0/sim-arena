# Sim-Arena AMI Setup Guide for Teammates

This guide explains how to **launch and use the prebuilt SimKube + SimArena AMI**. You do not set up from scratch — you start from the AMI and use the **S3-based trace workflow**.

---

## Quick Start

1. **Launch** an EC2 instance from AMI `simkube-simarena-s3-ready-2026-03-08` (ID: `ami-08d19a1b7f569b848`) in **us-east-2**.
2. **SSH** in: `ssh -i your_key.pem ubuntu@<EC2_PUBLIC_IP>` (after `chmod 400 your_key.pem`).
3. **Verify cluster:** `unset KUBECONFIG` then `kubectl get nodes` and `kubectl get pods -A`.
4. **Set env and secret:** `source ~/.bashrc`, then create the `simkube` Kubernetes secret with your AWS credentials (see §5).
5. **Run a test:** `cd ~/work/sim-arena && source .venv/bin/activate` then run `one_step.py` or `train.py` with an **S3 trace path** (e.g. `s3://your-bucket/demo/trace-mem-slight.msgpack`).

Details are below.

---

## AMI details

Use this AMI:

| Field | Value |
|-------|--------|
| **AMI name** | simkube-simarena-s3-ready-2026-03-08 |
| **AMI ID** | ami-08d19a1b7f569b848 |
| **Region** | us-east-2 (Ohio) |
| **Source AMI** | ami-01da5cfeb3e315b66 (SimKube Free AMI) |
| **Owner account** | 664926621123 |

This AMI already includes:

- SimKube
- sim-arena
- Python virtual environment and dependencies
- S3-based trace workflow support

---

## 1. Launch an EC2 instance from the AMI

**In AWS Console:**

1. Go to **EC2**
2. Go to **AMIs**
3. Find **simkube-simarena-s3-ready-2026-03-08**
4. Click **Launch instance from AMI**

**Recommended settings:**

- **Region:** us-east-2
- **Instance type:** at least **c6a.xlarge**
- **Key pair:** choose your SSH key
- **Security group:** allow SSH from your IP only
- **Storage:** 100 GB gp3 is a good default

Launch the instance and wait until:

- **Instance state** = Running
- **Status checks** = 2/2

---

## 2. SSH into the instance

From your laptop:

```bash
chmod 400 your_key.pem
ssh -i your_key.pem ubuntu@<EC2_PUBLIC_IP>
```

If SSH says the key permissions are too open:

```bash
chmod 400 your_key.pem
```

---

## 3. Verify the cluster is healthy

After SSHing in, run:

```bash
unset KUBECONFIG
kubectl get nodes
kubectl get pods -A
```

**Important:**

- **Do not** set `KUBECONFIG=/etc/kind/cluster` — `/etc/kind/cluster` is a **directory**, not the kubeconfig file.
- The instance already has the correct kubeconfig in `~/.kube/config`.

**Expected:**

- `cluster-control-plane` and `cluster-worker` should be **Ready**
- SimKube pods in namespace `simkube` should be running

---

## 4. Required environment variables

This AMI is intended to use **S3-hosted traces**.

Set these in your shell:

```bash
source ~/.bashrc
```

If needed, you can set them manually:

```bash
export AWS_ACCESS_KEY_ID=<your-access-key-id>
export AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
export AWS_DEFAULT_REGION=us-east-2

export SIM_ARENA_DRIVER_TIMEOUT=150
export SIM_ARENA_DEPLOY_TIMEOUT=90
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
export PYTHONPATH=/home/ubuntu/work/sim-arena
```

**Notes:**

- `SIM_ARENA_DRIVER_TIMEOUT` and `SIM_ARENA_DEPLOY_TIMEOUT` are increased because EC2 is slower than local runs.
- `SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster` is required because that is the SimKube node data path.

---

## 5. S3 + Kubernetes secret setup

Each cluster needs AWS credentials injected into the SimKube namespace so the driver can read traces from S3.

### 5.1 Create or update the simkube secret

Run on the EC2 instance:

```bash
kubectl create secret generic simkube -n simkube \
  --from-literal=AWS_ACCESS_KEY_ID=<your-access-key-id> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<your-secret-access-key> \
  --from-literal=AWS_DEFAULT_REGION=us-east-2 \
  --dry-run=client -o yaml | kubectl apply -f -
```

Then verify:

```bash
kubectl get secret -n simkube
```

Expected output includes **simkube**.

### 5.2 S3 bucket permissions

The IAM user used for the secret must have a policy that allows:

- `s3:GetObject`
- `s3:PutObject`
- `s3:ListBucket`
- `s3:DeleteObject`

for the relevant bucket.

**Example policy:**

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SimKubeAccessS3",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:ListBucket",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::YOUR-BUCKET-NAME",
        "arn:aws:s3:::YOUR-BUCKET-NAME/*"
      ]
    }
  ]
}
```

Replace `YOUR-BUCKET-NAME` with your bucket name.

---

## 6. Repository location

The repo is already on the instance here:

```bash
cd ~/work/sim-arena
source .venv/bin/activate
```

If you want the latest code:

```bash
git pull
```

---

## 7. Running a single-step test

Use an **S3 trace path**, for example:

```
s3://diya-simarena-traces/demo/trace-mem-slight.msgpack
```

Then run:

```bash
cd ~/work/sim-arena
source .venv/bin/activate
source ~/.bashrc

python runner/one_step.py \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent bump_cpu \
  --log-level INFO
```

**Expected successful output** includes lines like:

```
Deployment 'web' found
Observation: {'ready': 0, 'pending': 3, 'total': 3}
Step Summary: action=bump_cpu_small, reward=...
```

---

## 8. Running a short training test

Once `one_step.py` works, test training:

```bash
cd ~/work/sim-arena
source .venv/bin/activate
source ~/.bashrc

python runner/train.py \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --agent greedy \
  --episodes 2 \
  --steps 3 \
  --duration 40
```

Training logs are written under:

```
~/work/sim-arena/checkpoints/
```

---

## 9. Common problems

### `kubectl get nodes` says Forbidden

Run:

```bash
unset KUBECONFIG
kubectl get nodes
```

Do **not** point `KUBECONFIG` at `/etc/kind/cluster`.

---

### Deployment 'web' not found

Check:

- That the trace path exists in S3
- That the `simkube` secret exists in namespace `simkube`
- That the AWS credentials are valid
- That the bucket is in the expected region
- That the IAM policy includes S3 read permissions

Also check:

```bash
kubectl get pods -n simkube
kubectl logs -n simkube sk-ctrl-depl-<pod-name> --tail=100
```

---

### AccessDenied from S3

The IAM user does not have the right bucket permissions. Fix the policy and recreate/update the `simkube` secret.

---

### Load key "*.pem": bad permissions

Run on your laptop:

```bash
chmod 400 your_key.pem
```

---

### Too many open files

Run:

```bash
ulimit -n 4096
```

---

## 10. Daily workflow

**Start working**

1. Launch instance from AMI
2. SSH in
3. Run:

   ```bash
   cd ~/work/sim-arena
   source .venv/bin/activate
   source ~/.bashrc
   unset KUBECONFIG
   kubectl get nodes
   ```

4. Run `one_step.py` or `train.py` with S3 trace paths

**End of day**

- If you are done and do not need the instance: **terminate** it
- If you want to keep the same running machine: **stop** it
- If you changed the setup and want to preserve it for everyone: **create a new AMI**

---

## 11. Launch recipe

Keep this with the guide:

| Item | Value |
|------|--------|
| AMI name | simkube-simarena-s3-ready-2026-03-08 |
| AMI ID | ami-08d19a1b7f569b848 |
| Region | us-east-2 |
| Recommended instance type | c6a.xlarge |
| SSH user | ubuntu |
| Node data path | /var/kind/cluster |
| Repo path | ~/work/sim-arena |

---

## 12. Security note

**Do not** commit AWS access keys to GitHub or paste them into shared docs.

Use:

- IAM user with minimal S3 permissions
- Kubernetes secret in namespace `simkube`
- Rotated credentials if a key is ever exposed
