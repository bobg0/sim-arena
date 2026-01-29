## Worklog Summary (local changes)

This file records the important changes and cluster-side actions performed during debugging.

### Code changes
- Rebuilt `runner/one_step_copyb.py` as the active variant:
  - Uses `SimEnv.create(...)` so the driver image can be specified.
  - Logs trace version instead of coercing v1 → v2.
  - Keeps only essential logs: start, create, observe, action, reward, summary.
  - Adds CLI flag `--driver-image` (default `quay.io/appliedcomputing/sk-driver:v2.4.1`).
- Added `demo/convert_normalized_trace_to_json.py`:
  - Converts `demo/trace-normalized.msgpack` → `demo/trace-normalized.json`.

### Trace artifacts
- Normalized trace created by `one_step_copyb.py`:
  - `.tmp/trace-normalized.msgpack`
- Copied into demo folder:
  - `demo/trace-normalized.msgpack`
  - `demo/trace-normalized.json`
- Copied into kind node data for hostPath mounting:
  - `/home/bogao/.local/kind-node-data/cluster/trace-normalized.msgpack`

### Cluster-side actions (kubectl)
- Created namespace (when missing):
  - `kubectl create namespace test-ns`
- Added ServiceAccount required by driver job:
  - Created `sk-ctrl-sa` in `test-ns`
  - Bound it to `cluster-admin` via `ClusterRoleBinding` `sk-ctrl-sa-test-ns-crb`
- Copied Secret required by driver pod:
  - `kubectl get secret simkube -n simkube -o yaml | sed 's/namespace: simkube/namespace: test-ns/' | kubectl apply -f -`

### Runtime artifacts (from repeated runs)
- `.tmp/trace-next.msgpack` updated by runs
- `runs/step.jsonl` appended with step records
- `runs/summary.json` appended and totals updated

### What was tried
- Ran `one_step_copyb.py` repeatedly with:
  - `demo/trace-0001.msgpack`
  - `demo/trace-normalized.msgpack`
  - `file:///data/trace-0001.msgpack`
- Verified driver job/pod creation in `test-ns`.
- Fixed missing `sk-ctrl-sa` in `test-ns` (job creation failure).
- Fixed missing `simkube` secret in `test-ns` (pod startup failure).
- Fixed missing trace mount by copying trace into kind node data.

### Commands used to debug
- Run copyb:
  - `python3 runner/one_step_copyb.py --trace demo/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 120`
- Observe driver/job/pods:
  - `kubectl get simulations -A`
  - `kubectl get jobs -n test-ns`
  - `kubectl get pods -n test-ns`
  - `kubectl get pods -n test-ns -l app=web`
- Inspect failures:
  - `kubectl describe job -n test-ns <job-name>`
  - `kubectl describe pod -n test-ns <pod-name>`
  - `kubectl get events -n test-ns --sort-by=.lastTimestamp | tail -n 20`
  - `kubectl logs -n test-ns <driver-pod>`
  - `kubectl logs -n test-ns job/<driver-job>`

### Failure scenarios observed (in order)
1) **ServiceAccount missing**
   - Error: `serviceaccount "sk-ctrl-sa" not found`
   - Effect: driver Job cannot create a pod.
   - Fix: create `sk-ctrl-sa` in `test-ns` and bind it to `cluster-admin`.

2) **Trace mount missing**
   - Error: `hostPath type check failed: /data/trace-normalized.msgpack is not a file`
   - Effect: driver pod stuck in `ContainerCreating` then evicted.
   - Fix: copy normalized trace into kind node data at `/home/bogao/.local/kind-node-data/cluster/trace-normalized.msgpack`.

3) **Secret missing**
   - Error: `secret "simkube" not found`
   - Effect: driver container starts then exits.
   - Fix: copy secret from `simkube` namespace into `test-ns`.

4) **Trace parse failure (current)**
   - Error: `could not parse trace file` and "older than version 2"
   - Effect: driver container exits; job hits backoff limit; no workload pods.

### Current failure mode
- Driver pod starts but exits with:
  - `could not parse trace file`
  - Indicates trace format is older than v2 even when `version` field is set to 2.
- Result: driver crashes, no workload pods created, `observe()` stays at zero.

