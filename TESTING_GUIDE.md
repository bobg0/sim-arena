# Testing Guide - Quick Steps

## What I Fixed

**Bug**: `one_step.py` crashed with `AttributeError: 'str' object has no attribute 'get'`

**Fix**: Updated `_extract_current_state()` function in `runner/one_step.py` to properly parse trace format.
- Changed from iterating `trace` directly to `trace['events'][*]['applied_objs']`
- Fixed indentation issue

**File changed**: `runner/one_step.py` (lines 68-88)

---

## Current Status

✅ **Working**:
- Kubernetes cluster running (kind-sim-arena-test)
- SimKube CRD installed
- test-ns namespace created
- Your code runs without errors

⚠️ **Missing**:
- SimKube controller (sk-ctrl) not installed
- Without it, simulations don't actually create pods

---

## What To Do Next

### Step 1: Test the Bug Fix

Run this to verify the script works:

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
PYTHONPATH=. python runner/one_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 10 \
  --policy heuristic
```

**Expected**: Script completes successfully (exit code 0), but observations show 0 pods because SimKube driver isn't running yet.

---

### Step 2: Install SimKube Controller

This is what actually runs the simulations:

```bash
kubectl apply -k ~/clinic_ACRL/simkube/k8s/kustomize/sim
```

**What this does**: Installs `sk-ctrl` controller that watches for Simulation resources and creates/manages pods.

**Check if it's running**:
```bash
kubectl get pods -A | grep simkube
```

You should see a `sk-ctrl` pod running.

---

### Step 3: Run Full Test

Once sk-ctrl is running:

```bash
cd ~/clinic_ACRL/sim-arena
source .venv/bin/activate
PYTHONPATH=. python runner/one_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy heuristic
```

**Expected**: 
- Simulation created
- Pods appear in test-ns (you can check with `kubectl get pods -n test-ns`)
- Observations show actual pod counts
- Policy makes a decision based on pod states
- Reward calculated

---

### Step 4: Verify Multi-Step Works

Test learning over multiple episodes:

```bash
PYTHONPATH=. python runner/multi_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy heuristic \
  --steps 5
```

**Expected**:
- 5 episodes run
- Trace gets modified after each episode
- Observations change as resources are adjusted
- Reward should improve over time (0 → 1)

---

## Troubleshooting

### If SimKube controller install fails:

Check if Docker images exist:
```bash
docker images | grep simkube
```

If no images, you might need to build them first. Check:
```bash
cat ~/clinic_ACRL/simkube/README.md | grep -A 5 "build"
```

### If pods don't appear:

Check simulation status:
```bash
kubectl get simulations -A
kubectl describe simulation <simulation-name>
```

Check controller logs:
```bash
kubectl logs -n simkube-system <sk-ctrl-pod-name>
```

### If observations are always 0:

The issue is likely:
1. SimKube driver not running
2. Trace format incompatible with your SimKube version
3. Pods are created but in different namespace

---

## What To Expect

### Without SimKube controller:
```
Observation: {'ready': 0, 'pending': 0, 'total': 0}
Policy: noop (because no pods to fix)
Reward: 0
```

### With SimKube controller running:
```
Observation: {'ready': 0, 'pending': 4, 'total': 4}  # Pods pending due to high CPU
Policy: bump_cpu_small (tries to reduce CPU)
Reward: 0 (not all pods ready yet)
```

After multiple episodes, CPU gets reduced → pods become ready → reward becomes 1.

---

## Summary

**Run these in order:**

1. Test script works: `PYTHONPATH=. python runner/one_step.py --trace demo/traces/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 10 --policy heuristic`

2. Install SimKube: `kubectl apply -k ~/clinic_ACRL/simkube/k8s/kustomize/sim`

3. Verify controller: `kubectl get pods -A | grep simkube`

4. Test again: Run step 1 again with `--duration 60`

5. Test multi-step: `PYTHONPATH=. python runner/multi_step.py --trace demo/traces/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 60 --policy heuristic --steps 5`

---

## Files Changed

Only 1 file was modified:
- `runner/one_step.py` - Fixed trace parsing bug

You can see the changes with:
```bash
git diff runner/one_step.py
```

To commit:
```bash
git add runner/one_step.py
git commit -m "Fix trace parsing bug in _extract_current_state"
```
