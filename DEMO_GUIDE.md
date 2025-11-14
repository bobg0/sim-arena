# Quick Demo Guide

## Pre-Demo Setup (5 minutes)

### 1. Install Dependencies

**Option A: User install (recommended for demo)**
```bash
pip3 install --user -r requirements.txt
```

**Option B: Virtual environment**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Verify Setup

```bash
# Check cluster access
kubectl cluster-info

# Run preflight checks
make preflight
```

### 3. Prepare Namespace

```bash
# Create namespace if it doesn't exist
kubectl create namespace test-ns

# Clean namespace (optional, removes all pods)
make clean-ns
```

## Running the Demo

### Quick Run (2 minutes)

```bash
# Set PYTHONPATH and run
PYTHONPATH=. python3 runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60
```

### Using Convenience Script

```bash
# Make sure sk-run is executable
chmod +x sk-run

# Run
./sk-run \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60
```

### What Happens

1. **Pre-start hook**: Deletes all pods in `test-ns`
2. **Create simulation**: Creates SimKube Simulation CR
3. **Wait**: Waits 60 seconds (or your specified duration)
4. **Observe**: Reads pod states
5. **Policy**: If pods are pending, bumps CPU
6. **Reward**: Computes reward (1 if target met, 0 otherwise)
7. **Log**: Writes to `runs/step.jsonl` and `runs/summary.json`
8. **Cleanup**: Deletes simulation

### View Results

```bash
# View last step
tail -1 runs/step.jsonl | python3 -m json.tool

# View summary
cat runs/summary.json | python3 -m json.tool

# View all steps
cat runs/step.jsonl | python3 -m json.tool
```

### Check Cluster State

```bash
# View pods
kubectl get pods -n test-ns

# View simulations
kubectl get simulations -n test-ns

# View simulation details
kubectl get simulation <sim-name> -n test-ns -o yaml
```

## Troubleshooting

### Dependencies Not Found

```bash
# Install with --user flag
pip3 install --user kubernetes msgpack pytest

# Or use virtual environment
python3 -m venv venv && source venv/bin/activate && pip install -r requirements.txt
```

### Module Import Errors

```bash
# Always set PYTHONPATH
export PYTHONPATH=.
# Or use inline
PYTHONPATH=. python3 runner/one_step.py ...
```

### Cluster Connection Issues

```bash
# Verify kubectl works
kubectl cluster-info
kubectl get nodes

# Check namespace exists
kubectl get namespace test-ns
```

### CRD Not Found

The code will automatically fall back to ConfigMap if CRD is not available. This is fine for demo purposes.

## Demo Script (Copy-Paste Ready)

```bash
#!/bin/bash
set -e

echo "=== Sim-Arena Demo ==="
echo ""

# Install dependencies (if needed)
echo "1. Checking dependencies..."
pip3 install --user -q kubernetes msgpack pytest || true

# Preflight
echo "2. Running preflight checks..."
make preflight || echo "Warning: Preflight failed, continuing anyway..."

# Clean namespace
echo "3. Cleaning namespace..."
make clean-ns || echo "Warning: Clean failed, continuing anyway..."

# Run one step
echo "4. Running one agent step..."
PYTHONPATH=. python3 runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --seed 42

# Show results
echo ""
echo "5. Results:"
echo "--- Step Record ---"
tail -1 runs/step.jsonl | python3 -m json.tool
echo ""
echo "--- Summary ---"
cat runs/summary.json | python3 -m json.tool

echo ""
echo "=== Demo Complete ==="
```

Save as `demo.sh`, make executable: `chmod +x demo.sh`, then run: `./demo.sh`

