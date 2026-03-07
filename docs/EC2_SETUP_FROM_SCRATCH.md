# Sim-Arena on EC2 — Setup from Scratch

Complete guide for a **new EC2 instance** with SimKube. Do these steps in order.

---

## Part 1: SSH into EC2

```bash
# From your Mac
chmod 400 your_key.pem
ssh -i your_key.pem ubuntu@<EC2_PUBLIC_IP>
```

**If `Permission denied`:** run `chmod 400 your_key.pem` on the key file.

---

## Part 2: Fix kubectl (important on new instances)

SimKube may pre-create a placeholder. Use the correct kubeconfig:

```bash
# /etc/kind/cluster is a DIRECTORY, not the config file. Do NOT set KUBECONFIG to it.
unset KUBECONFIG

# kubectl uses ~/.kube/config by default
kubectl get nodes
kubectl get pods -A
```

**If `kubectl get nodes` fails with Forbidden:** `unset KUBECONFIG` and try again.  
**If you see `read /etc/kind/cluster: is a directory`:** you set KUBECONFIG wrong; unset it.

---

## Part 3: Cluster permissions

```bash
# Node data path (SimKube prints this on login)
sudo chown -R ubuntu:ubuntu /var/kind/cluster
```

---

## Part 4: S3 setup (advisor’s instructions)

Do this so the SimKube driver can read traces from S3. **Do it once per cluster.**

### 4.1 Create S3 bucket (AWS Console)

- S3 → Create bucket → pick a name (e.g. `simkube-traces`)
- Region: same as your EC2
- Create

### 4.2 Create IAM policy

IAM → Policies → Create policy → JSON:

```json
{
    "Statement": [
        {
            "Action": [
                "s3:PutObject",
                "s3:GetObject",
                "s3:ListBucket",
                "s3:DeleteObject"
            ],
            "Effect": "Allow",
            "Resource": [
                "arn:aws:s3:::YOUR-BUCKET-NAME/*",
                "arn:aws:s3:::YOUR-BUCKET-NAME"
            ],
            "Sid": "SimKubeAccessS3"
        }
    ],
    "Version": "2012-10-17"
}
```

Replace `YOUR-BUCKET-NAME` with your bucket. Or use `"Resource": ["*"]` for all buckets.

Name the policy (e.g. `SimKubeS3Access`) → Create.

### 4.3 Create IAM user and access key

- IAM → Users → Create user (e.g. `simkube-s3`)
- Attach the policy you created
- Create user
- Open the user → Security credentials → Create access key
- Choose “Application running outside AWS” (or similar)
- **Save Access Key ID and Secret Access Key** — the secret is shown only once

**Do not commit these to GitHub or share them.**

### 4.4 Create Kubernetes secret on EC2

SSH into EC2, then:

```bash
kubectl create secret generic simkube -n simkube \
  --from-literal=AWS_ACCESS_KEY_ID=<your-access-key-id> \
  --from-literal=AWS_SECRET_ACCESS_KEY=<your-secret-access-key>
```

**If `secrets "simkube" already exists`:**

```bash
kubectl delete secret -n simkube simkube
# Then re-run the create command above
```

**Optional:** Bake this into a new AMI so you don’t repeat it on new instances.

### 4.5 Using S3 traces

With the secret in place, the SimKube driver can use `s3://your-bucket/path/to/trace.msgpack` as the trace path. **sim-arena currently uses local files** (see Part 6). S3 is for `skctl` or future sim-arena support.

---

## Part 5: sim-arena setup

### 5.1 System packages

```bash
sudo apt-get update -y
sudo apt-get install -y git python3-venv python3-pip
```

If you see `Too many open files`: `ulimit -n 4096`

### 5.2 Clone and install

```bash
mkdir -p ~/work
cd ~/work
git clone https://github.com/bobg0/sim-arena.git
cd sim-arena

python3 -m venv .venv
source .venv/bin/activate
pip install -U pip wheel
pip install -r requirements.txt
```

*(Torch + CUDA can take 10–20 minutes.)*

### 5.3 Environment variables

```bash
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
export PYTHONPATH=.
```

**If you hit `--virtual-ns-prefix` driver error** (older SimKube controller):

```bash
export SIM_ARENA_DRIVER_IMAGE=quay.io/appliedcomputing/sk-driver:v2.4.0
```

---

## Part 6: Run a test (local file traces)

sim-arena uses **local files** by default. Copy the trace to the node data path:

```bash
cd ~/work/sim-arena
source .venv/bin/activate
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
export PYTHONPATH=.
# Add if needed: export SIM_ARENA_DRIVER_IMAGE=quay.io/appliedcomputing/sk-driver:v2.4.0

cp demo/trace-0001.msgpack /var/kind/cluster/

python runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns virtual-default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent bump_cpu \
  --log-level INFO
```

**Expected:** Simulation created, driver runs, observation printed.

### Short training run

```bash
python runner/train.py \
  --trace demo/trace-0001.msgpack \
  --ns virtual-default \
  --deploy web \
  --target 3 \
  --agent greedy \
  --episodes 2 \
  --steps 5 \
  --duration 40
```

---

## Part 7: Optional — CPU-only PyTorch

If you don’t need GPU:

```bash
pip uninstall torch -y
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Load key "*.pem": bad permissions` | `chmod 400 your_key.pem` |
| `kubectl get nodes` → Forbidden or `is a directory` | `unset KUBECONFIG` |
| `Too many open files` | `ulimit -n 4096` |
| Trace not found | `ls /var/kind/cluster/` — trace must be there; set `SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster` |
| Deployment 'web' not found (404) | Driver slow or failing. Check logs: `kubectl logs -n simkube -l job-name=sk-<sim_name>-driver` |
| `error: unexpected argument '--virtual-ns-prefix' found` | `export SIM_ARENA_DRIVER_IMAGE=quay.io/appliedcomputing/sk-driver:v2.4.0` |
| Many pods in Error/CrashLoopBackOff | Wait 3–5 min after instance start. If it persists, ask your advisor. |

---

## Quick reference — full run

```bash
cd ~/work/sim-arena && source .venv/bin/activate
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
export PYTHONPATH=.
# export SIM_ARENA_DRIVER_IMAGE=quay.io/appliedcomputing/sk-driver:v2.4.0  # if needed

cp demo/trace-0001.msgpack /var/kind/cluster/
python runner/one_step.py --trace demo/trace-0001.msgpack --ns virtual-default --deploy web --target 3 --duration 40 --agent bump_cpu --log-level INFO
```
