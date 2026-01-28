# SimKube Driver Not Creating Pods - Need Help

**Date**: 2026-01-27  
**Environment**: macOS, kind cluster, SimKube installed via isengard  
**Issue**: Simulations are created successfully but no pods appear in target namespace

---

## Summary

When running `one_step.py` to create a SimKube simulation, the simulation CR is created and sk-ctrl processes it, but **no pods are ever created** in the target namespace. Observations always show `{'ready': 0, 'pending': 0, 'total': 0}`.

---

## What Works ✅

1. **Kubernetes cluster is running** (after fresh rebuild with latest isengard updates)
   - `kind get clusters` shows `cluster`
   - All control plane pods running

2. **SimKube controllers installed and running**:
   ```bash
   $ kubectl get pods -n simkube
   NAME                             READY   STATUS    RESTARTS   AGE
   sk-ctrl-depl-65bf694576-kt28q    1/1     Running   0          10m
   sk-tracer-depl-bb4659fc7-k5tdx   1/1     Running   0          10m
   ```

3. **Simulation CRD exists**:
   ```bash
   $ kubectl get crd | grep simulation
   simulationroots.simkube.io    2026-01-28T00:22:08Z
   simulations.simkube.io        2026-01-28T00:22:09Z
   ```

4. **Simulation CR created successfully**:
   ```bash
   $ kubectl get simulations -A
   # Shows simulation being created, then deleted after script cleanup
   ```

5. **Python code works**:
   - Script executes without errors
   - Trace file loads successfully
   - Policies run correctly
   - Observations retrieved (but always 0 pods)

---

## What Doesn't Work ❌

**No pods are created in the target namespace (`test-ns`)**

Even after waiting 120 seconds, the namespace remains empty:
```bash
$ kubectl get pods -n test-ns
No resources found in test-ns namespace.
```

Observations always return:
```
{'ready': 0, 'pending': 0, 'total': 0}
```

---

## Setup Details

### Cluster Setup
```bash
cd ~/clinic_ACRL/isengard
git pull  # Latest: commit a222e68 (includes SimKube 2.4.1)
kind delete clusters --all
just run simkube
```

### Trace File
- Located at: `demo/trace-0001.msgpack`
- Copied to: `/Users/diyagangwar/.local/kind-node-data/cluster/trace-0001.msgpack`
- Trace content (from JSON version):
  ```json
  {
    "version": 1,
    "events": [{
      "ts": 1730390400,
      "applied_objs": [{
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": "web", "namespace": "default"},
        "spec": {
          "replicas": 2,
          "template": {
            "spec": {
              "containers": [{
                "name": "web",
                "image": "ghcr.io/example/web:1.0",
                "resources": {
                  "requests": {"cpu": "500m", "memory": "512Mi"}
                }
              }]
            }
          }
        }
      }]
    }]
  }
  ```

### Simulation Spec
Created by our code:
```yaml
apiVersion: simkube.io/v1
kind: Simulation
metadata:
  name: diag-636c593b
spec:
  driver:
    image: ghcr.io/simkube/sk-driver:latest
    namespace: test-ns
    port: 8080
    tracePath: file:///data/trace-0001.msgpack
  duration: 120s
```

---

## Diagnostic Logs

### sk-ctrl logs during simulation (diag-636c593b)

**Initial setup (successful)**:
```
2026-01-28T00:45:55.319161Z INFO reconciling object: Simulation.v1.simkube.io/diag-636c593b
2026-01-28T00:45:55.322588Z INFO creating Simulation MetaRoot simulation="diag-636c593b"
2026-01-28T00:45:55.327856Z INFO trying to acquire lease simulation="diag-636c593b"
2026-01-28T00:45:55.334169Z INFO setting up simulation simulation="diag-636c593b"
2026-01-28T00:45:55.337312Z INFO creating driver namespace test-ns simulation="diag-636c593b"
2026-01-28T00:45:55.341178Z INFO creating driver service sk-diag-636c593b-driver-svc
2026-01-28T00:45:55.348773Z INFO creating cert-manager certificate sk-driver-cert
2026-01-28T00:45:55.355325Z INFO waiting for secret to be created simulation="diag-636c593b"
```

**Driver creation attempted (but fails later)**:
```
2026-01-28T00:46:00.399371Z INFO creating simulation driver sk-diag-636c593b-driver
2026-01-28T00:46:00.404745Z INFO related object updated: Job.v1.batch/sk-diag-636c593b-driver.test-ns
```

**Error during cleanup**:
```
2026-01-28T00:47:55.456657Z ERROR reconcile failed on simulation diag-636c593b
ApiError: jobs.batch "sk-diag-636c593b-driver" is forbidden: unable to create new content 
in namespace test-ns because it is being terminated: Forbidden
```

### Pattern Observed

1. Simulation CR created ✅
2. sk-ctrl processes it ✅
3. Driver namespace created ✅
4. Driver service created ✅
5. Certificate created ✅
6. Driver job creation attempted ✅
7. **But no driver pod ever appears** ❌
8. No pods created in test-ns ❌
9. When script tries to delete simulation, namespace is terminating (error)

---

## What We've Tried

1. ✅ **Rebuilt cluster from scratch** (multiple times)
2. ✅ **Pulled latest isengard updates** (now on SimKube 2.4.1)
3. ✅ **Verified trace file path is accessible** (`file:///data/trace-0001.msgpack`)
4. ✅ **Checked all SimKube pods are healthy** (both sk-ctrl and sk-tracer running)
5. ✅ **Increased wait duration** (tried 60s, 120s)
6. ✅ **Verified namespace exists before simulation** (test-ns created by pre_start hook)
7. ✅ **Checked for stuck simulations** (cleaned up any existing ones)
8. ✅ **Reduced cluster load** (deleted other kind clusters)

---

## Questions for SimKube Team

1. **Is the trace file format correct?** 
   - Using `.msgpack` files with structure shown above
   - Path: `file:///data/trace-0001.msgpack`

2. **Should we see a driver pod?**
   - Expected: `sk-diag-<id>-driver` pod in `test-ns`
   - Actual: No driver pods ever appear

3. **Why does the driver job creation succeed but no pod appears?**
   - Logs show: "creating simulation driver sk-diag-<id>-driver"
   - But: `kubectl get pods -n test-ns` always empty
   - And: `kubectl get jobs -n test-ns` shows nothing

4. **Is there a working example we can reference?**
   - Example trace file?
   - Example simulation creation?
   - Expected output when working correctly?

5. **Any known issues with SimKube 2.4.1 on kind/local clusters?**

6. **Should the driver create resources in the SAME namespace (test-ns)?**
   - Or does it create them elsewhere?
   - Our observation code looks in test-ns - is that correct?

---

## Environment Details

- **OS**: macOS (darwin 25.2.0)
- **Kind version**: Latest (from brew)
- **Kubernetes version**: v1.34.0 (from kind)
- **SimKube version**: 2.4.1 (from isengard commit a222e68)
- **Python**: 3.x (in virtualenv)

### Cluster Info
```bash
$ kubectl cluster-info
Kubernetes control plane is running at https://127.0.0.1:64551

$ kubectl get nodes
NAME                    STATUS   ROLES           AGE   VERSION
cluster-control-plane   Ready    control-plane   15m   v1.34.0
cluster-worker          Ready    <none>          15m   v1.34.0
node1                   Ready    <none>          15m   v1.34.0
node2                   Ready    <none>          15m   v1.34.0
node3                   Ready    <none>          15m   v1.34.0
```

---

## Code Reference

Our simulation creation code: `env/sim_env.py` (lines 37-77)

```python
def create(self, name, trace_path, namespace, duration_s,
           driver_image: str = "ghcr.io/simkube/sk-driver:latest", 
           driver_port: int = 8080):
    body = {
        "apiVersion": f"{SIM_GROUP}/{SIM_VER}",
        "kind": "Simulation",
        "metadata": {"name": name},
        "spec": {
            "driver": {
                "image": driver_image,
                "namespace": namespace,
                "port": int(driver_port),
                "tracePath": trace_path,
            },
            "duration": f"{int(duration_s)}s",
        },
    }
    self.custom.create_cluster_custom_object(
        group=SIM_GROUP, version=SIM_VER,
        plural=SIM_PLURAL, body=body
    )
```

---

## Diagnostic Test Results

Run this to diagnose the specific issue:
```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
python test_zero_diagnosis.py
```

This test checks:
1. ✅ Kubernetes API connection
2. ✅ test-ns namespace exists
3. ❌ **Pods in test-ns** (FAILING - this is the issue)
4. ❌ Pods with label app=web in test-ns
5. ✅ Simulation CRD installed
6. ✅ SimKube controllers running
7. ⚠️  Simulation activity
8. ⚠️  Check if pods in 'default' namespace (trace mismatch)

**Key Finding**: All infrastructure is working, but **no pods are being created from simulations**.

---

## Next Steps

We need help understanding:
1. What's preventing pods from being created from simulations?
2. Should we see a driver pod that replays the trace?
3. Is there a configuration issue with our trace files or simulation specs?
4. Are there any SimKube logs showing errors during simulation processing?

Any guidance would be greatly appreciated!

---

## Contact

- GitHub: [Link to sim-arena repo if public]
- This issue document: `SIMKUBE_ISSUE.md`
