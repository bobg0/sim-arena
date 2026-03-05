# Sim-Arena on AWS EC2

Quick guide to get sim-arena running on an EC2 instance with SimKube pre-installed.

---

## Prerequisites (you've done these)

- [x] SSH into EC2 with your `.pem` key (`chmod 400` if needed)
- [x] SimKube cluster running (`kubectl get nodes` shows Ready)
- [x] `skctl` available
- [x] Git, Python 3, pip installed
- [x] sim-arena cloned, venv created, `pip install -r requirements.txt` (wait for it to finish)

---

## 1. Wait for pip to finish

If `pip install -r requirements.txt` is still running (torch + CUDA are large), let it complete.

---

## 2. Verify kubectl and KUBECONFIG

Sim-arena uses the Kubernetes Python client, which reads `~/.kube/config` by default.

```bash
# Check kubectl works
kubectl get nodes
kubectl get pods -A

# If kubectl works, the default config is fine. If not:
export KUBECONFIG=/etc/kind/cluster  # or wherever your kubeconfig lives
```

---

## 3. Trace file path (node data directory)

SimKube needs trace files in the **node data path** so the driver can read them at `file:///data/<filename>`.

**On your EC2**, the SimKube message said:
- Node data path: `/var/kind/cluster`

**Sim-arena** by default copies traces to `~/.local/kind-node-data/<namespace>`. On EC2, that path may not be mounted. Use the env override:

```bash
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster
```

**Permissions**: You need write access to that directory. If it's root-owned:

```bash
sudo chown -R ubuntu:ubuntu /var/kind/cluster
# or
sudo chmod 777 /var/kind/cluster  # less secure, but quick for testing
```

---

## 4. Run a quick test (one step)

**Note:** sim-arena creates Simulation CRs via the Kubernetes API—it does **not** use `skctl`. The `skctl run` command needs SimKube config files (`config/hooks/`) that are not in sim-arena; you can ignore skctl and use sim-arena directly.

```bash
cd ~/work/sim-arena
source .venv/bin/activate
export SIM_ARENA_NODE_DATA_DIR=/var/kind/cluster   # if needed
export PYTHONPATH=.

# Single step with bump_cpu policy (fastest sanity check)
python runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns virtual-default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent bump_cpu \
  --log-level INFO
```

**Expected**: Simulation CR created, driver runs, pods appear in `virtual-default`, observation printed, trace updated.

**If it fails**:
- `Permission denied` on trace copy → fix `/var/kind/cluster` permissions
- `Simulation CRD not found` → SimKube controllers may not be fully installed
- `No pods` → check `kubectl get pods -n virtual-default` and `kubectl get pods -n simkube`

---

## 5. Run a short training episode

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

## 6. Optional: CPU-only PyTorch (faster install)

If you don't need GPU on EC2, you can install CPU-only torch to avoid the large CUDA download:

```bash
pip uninstall torch -y
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| `Load key "*.pem": bad permissions` | `chmod 400 your_key.pem` |
| `Too many open files` | `ulimit -n 4096` (or higher) |
| Trace not found by driver | Ensure `SIM_ARENA_NODE_DATA_DIR` points to the node data path; check `ls /var/kind/cluster/` |
| No pods in virtual-default | Check SimKube controller logs: `kubectl logs -n simkube -l app=sk-ctrl` |
| `kubectl` not found or wrong cluster | Set `KUBECONFIG` to the correct config path |
