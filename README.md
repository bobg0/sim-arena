# Sim-Arena MVP

A reinforcement learning environment for Kubernetes autoscaling using SimKube. This MVP implements a single, reproducible agent step that can be run end-to-end on a real Kubernetes cluster.

## Overview

Sim-Arena provides:
- **Environment**: Create and manage SimKube simulations
- **Observations**: Monitor pod states (ready, pending, total)
- **Actions**: Modify traces (CPU/memory bumps, replica scaling)
- **Rewards**: Binary reward based on target pod state
- **Runner**: Orchestrate one complete agent step

## Prerequisites

- Python 3.8+
- Kubernetes cluster with SimKube installed
- `kubectl` configured to access your cluster
- Access to a namespace (default: `test-ns`)

## Installation

1. **Clone the repository** (if not already done):
   ```bash
   cd sim-arena
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Verify cluster access**:
   ```bash
   make preflight
   ```
   This checks:
   - Kubernetes API connectivity
   - Namespace existence
   - SimKube CRD installation

## Quick Start

### 1. Run Preflight Checks

```bash
make preflight
```

### 2. Clean Namespace (Optional)

Before running, you may want to clean the test namespace:

```bash
make clean-ns
```

### 3. Run One Agent Step

Run a complete agent step using the demo trace:

```bash
python runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 120
```

Or use the convenience script:

```bash
./sk-run \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 120
```

### 4. Check Results

After running, check the logs:

```bash
# View step-by-step records
cat runs/step.jsonl

# View summary
cat runs/summary.json
```

## Usage

### Running One Step

The `one_step` function orchestrates a complete agent step:

1. **Pre-start hook**: Cleans namespace (deletes all pods)
2. **Create simulation**: Creates a SimKube Simulation CR
3. **Wait fixed**: Waits for the specified duration
4. **Observe**: Reads pod states (ready, pending, total)
5. **Policy decision**: Simple heuristic (if pending > 0, bump CPU)
6. **Apply action**: Modifies trace if needed
7. **Compute reward**: Binary reward (1 if target met, 0 otherwise)
8. **Log results**: Writes to `runs/step.jsonl` and `runs/summary.json`
9. **Cleanup**: Deletes the simulation CR

#### Command-Line Arguments

```bash
python runner/one_step.py \
  --trace <path>        # Path to input trace (msgpack format)
  --ns <namespace>      # Kubernetes namespace
  --deploy <name>       # Deployment name to observe
  --target <number>     # Target total number of pods
  --duration <seconds>  # Duration to wait (default: 120)
  --seed <number>       # Random seed (default: 0)
```

#### Example

```bash
python runner/one_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --seed 42
```

### Other CLI Tools

#### Environment Management

```bash
# Create a simulation
python sk_env_run.py \
  --name diag-0001 \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --duration 120

# Or use the wrapper
./sk-env \
  --name diag-0001 \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --duration 120
```

#### Actions

```bash
# Apply an action to a trace
./sk-action apply \
  --in demo/trace-0001.msgpack \
  --out demo/trace-modified.msgpack \
  --deploy web \
  --op bump_cpu_small \
  --step 500m
```

#### Observations

```bash
# Print current observation
python observe/print_obs.py --ns test-ns
```

## Project Structure

```
sim-arena/
├── env/                 # Environment module (SimKube integration)
│   ├── sim_env.py       # SimEnv class
│   ├── __init__.py      # Wrapper functions
│   └── actions/         # Trace actions
│       ├── trace_io.py  # Load/save traces (MessagePack)
│       └── ops.py        # Action operations (CPU, memory, replicas)
├── observe/             # Observation and reward
│   ├── reader.py        # Read pod states
│   ├── reward.py        # Compute rewards
│   └── print_obs.py     # CLI tool
├── ops/                 # Operations and hooks
│   ├── hooks.py         # Pre/post hooks
│   └── preflight.py     # Preflight checks
├── runner/              # Agent runner
│   └── one_step.py      # One-step orchestration
├── tests/               # Test suite
│   ├── test_observe.py
│   ├── test_ops.py
│   ├── test_trace_io.py
│   └── test_runner_integration.py
├── demo/                # Demo traces
│   ├── trace-0001.json
│   └── trace-0001.msgpack
├── runs/                # Runtime logs (created automatically)
│   ├── step.jsonl       # Step-by-step records
│   └── summary.json     # Summary statistics
├── Makefile             # Common tasks
├── requirements.txt       # Python dependencies
└── README.md            # This file
```

## Testing

### Run All Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_observe.py -v
pytest tests/test_ops.py -v
pytest tests/test_runner_integration.py -v
```

### Test Coverage

- **Unit tests**: Test individual functions with mocked dependencies
- **Integration tests**: Test full `one_step()` flow with mocked Kubernetes API

### Manual Testing on Real Cluster

1. **Preflight check**:
   ```bash
   make preflight
   ```

2. **Clean namespace**:
   ```bash
   make clean-ns
   ```

3. **Run one step**:
   ```bash
   python runner/one_step.py \
     --trace demo/trace-0001.msgpack \
     --ns test-ns \
     --deploy web \
     --target 3 \
     --duration 60
   ```

4. **Verify results**:
   ```bash
   # Check logs
   cat runs/step.jsonl | jq .
   cat runs/summary.json | jq .
   
   # Check cluster state
   kubectl get pods -n test-ns
   kubectl get simulations -n test-ns
   ```

## Troubleshooting

### Common Issues

#### 1. Kubernetes API Connection Failed

**Error**: `Failed to connect to Kubernetes API`

**Solutions**:
- Verify `kubectl` is configured: `kubectl cluster-info`
- Check `~/.kube/config` exists and is valid
- If running in-cluster, ensure service account has proper permissions

#### 2. CRD Not Found

**Error**: `CRD not installed` or `simulations.simkube.io not found`

**Solutions**:
- Verify SimKube is installed: `kubectl get crd simulations.simkube.io`
- Check CRD group/version matches: `kubectl api-resources --api-group=simkube.io`
- The code will fall back to ConfigMap if CRD is not available

#### 3. Namespace Not Found

**Error**: `Namespace 'test-ns' not found`

**Solutions**:
- Create the namespace: `kubectl create namespace test-ns`
- Or use an existing namespace: `--ns <your-namespace>`

#### 4. Import Errors

**Error**: `ModuleNotFoundError` or `failed to import`

**Solutions**:
- Ensure you're in the `sim-arena` directory
- Set `PYTHONPATH=.` if needed: `PYTHONPATH=. python runner/one_step.py ...`
- Verify dependencies are installed: `pip install -r requirements.txt`

#### 5. Trace File Not Found

**Error**: `Trace not found: demo/trace-0001.msgpack`

**Solutions**:
- Generate the msgpack file: `python demo/make_demo_trace.py`
- Or use the JSON version and convert it
- Verify the path is correct (relative to current directory)

#### 6. Deployment Not Found in Trace

**Error**: `bump_cpu_small returned False (deployment not found)`

**Solutions**:
- Verify the deployment name matches: `--deploy web` should match trace
- Check trace structure: `python -c "from env.actions.trace_io import load_trace; print(load_trace('demo/trace-0001.msgpack'))"`

#### 7. Permission Denied

**Error**: `403 Forbidden` or `Unauthorized`

**Solutions**:
- Check RBAC permissions for your service account/user
- Verify you can create/delete simulations: `kubectl auth can-i create simulations.simkube.io`
- Check namespace permissions: `kubectl auth can-i create pods -n test-ns`

### Debug Mode

Enable verbose logging by modifying `runner/one_step.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO to DEBUG
    ...
)
```

### Check Logs

All step records are logged to:
- `runs/step.jsonl`: One JSON object per line
- `runs/summary.json`: Aggregated summary

View with:
```bash
# Pretty print last step
tail -1 runs/step.jsonl | jq .

# View summary
cat runs/summary.json | jq .
```

## Architecture

### Flow Diagram

```
┌─────────────┐
│  Preflight  │  Check cluster, namespace, CRD
└──────┬──────┘
       │
┌──────▼──────┐
│ Pre-start   │  Clean namespace (delete pods)
│   Hook      │
└──────┬──────┘
       │
┌──────▼──────┐
│   Create    │  Create SimKube Simulation CR
│ Simulation  │
└──────┬──────┘
       │
┌──────▼──────┐
│ Wait Fixed  │  Wait for duration (e.g., 120s)
└──────┬──────┘
       │
┌──────▼──────┐
│  Observe    │  Read pod states (ready, pending, total)
└──────┬──────┘
       │
┌──────▼──────┐
│   Policy    │  Simple heuristic: if pending > 0 → bump CPU
└──────┬──────┘
       │
┌──────▼──────┐
│   Action    │  Modify trace (if needed)
└──────┬──────┘
       │
┌──────▼──────┐
│   Reward    │  Binary: 1 if target met, 0 otherwise
└──────┬──────┘
       │
┌──────▼──────┐
│    Log      │  Write to step.jsonl and summary.json
└──────┬──────┘
       │
┌──────▼──────┐
│  Cleanup    │  Delete Simulation CR
└─────────────┘
```

### Key Components

- **SimEnv**: Manages SimKube Simulation CRs (create, wait, delete)
- **Observe**: Reads Kubernetes pod states via API
- **Actions**: Modifies traces (CPU, memory, replicas)
- **Reward**: Computes binary reward based on target state
- **Runner**: Orchestrates the complete flow

## Development

### Adding New Actions

1. Add function to `env/actions/ops.py`:
   ```python
   def my_action(obj: dict, deploy: str, ...) -> bool:
       # Modify trace
       return True
   ```

2. Update `sk-action` CLI to support it

3. Add tests to `tests/test_ops.py`

### Adding New Observations

1. Add function to `observe/reader.py`:
   ```python
   def my_observation(namespace: str, ...) -> dict:
       # Query Kubernetes
       return {...}
   ```

2. Update `observe/print_obs.py` if needed

3. Add tests to `tests/test_observe.py`

### Modifying Policy

Edit `simple_policy()` in `runner/one_step.py`:

```python
def simple_policy(obs: dict, deploy: str):
    # Your policy logic here
    if condition:
        return {"type": "bump_cpu_small", "deploy": deploy}
    return {"type": "noop"}
```

## License

[Add license information here]

## Contributing

[Add contributing guidelines here]

## Status

**MVP Status**: ~95% Complete

All core functionality is implemented and tested. The MVP is ready for end-to-end testing on a real cluster.

See `STATUS_REPORT.md` for detailed progress and remaining tasks.

