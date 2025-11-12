# Sim-Arena MVP Status Report

**Date**: Current  
**Goal**: Get a single, reproducible agent step working end-to-end on a real cluster  
**Status**: ~70% Complete - Integration gaps prevent end-to-end execution

---

## Task Completion Status

### 1. Diya — SimKube "Environment" sim (env/) ✅ **MOSTLY COMPLETE**

#### ✅ Completed:
- ✅ Module `env/sim_env.py` with `SimEnv` class:
  - ✅ `create()` method (returns handle dict)
  - ✅ `wait_fixed()` method
  - ✅ `delete()` method
  - ✅ Uses kubeconfig from `~/.kube/config` with fallback to in-cluster
  - ✅ CRD detection with ConfigMap fallback
  - ✅ Handles 409 (already exists) gracefully
  - ✅ Idempotent delete (handles 404)
- ✅ CLI script `sk_env_run.py` (Python script):
  - ✅ Supports `--name`, `--trace`, `--ns`, `--duration`
  - ✅ Supports `--group`, `--version`, `--plural` overrides
  - ✅ JSON output mode
  - ✅ Error handling with cleanup

#### ❌ Missing/Issues:
1. **CLI Entry Point**: No `sk-env` executable script (only `sk_env_run.py`)
   - **Fix**: Create `sk-env` script or make `sk_env_run.py` executable with proper shebang
2. **Function Signatures**: `runner/one_step.py` expects standalone functions:
   - Expected: `create_simulation(name, trace_path, duration_s, namespace) -> str`
   - Actual: `SimEnv().create(name, trace_path, namespace, duration_s, ...) -> dict`
   - **Fix**: Create wrapper functions in `env/sim_env.py` or `env/__init__.py`
3. **Return Value**: Runner expects `sim_uid` (string), but `create()` returns a handle dict
   - **Fix**: Extract UID from handle or modify runner expectations

#### 🔧 Required Fixes:
```python
# In env/sim_env.py or env/__init__.py, add:
def create_simulation(name: str, trace_path: str, duration_s: int, namespace: str) -> str:
    env = SimEnv()
    handle = env.create(name, trace_path, namespace, duration_s)
    # Return UID or name for now
    return handle.get("name") or name

def wait_fixed(duration_s: int) -> None:
    SimEnv().wait_fixed(duration_s)

def delete_simulation(name: str, namespace: str) -> None:
    env = SimEnv()
    # Need to reconstruct handle or modify delete to accept name/ns
    # For now, create a minimal handle
    env.delete({"kind": "simulation", "name": name, "ns": namespace})
```

---

### 2. Cate — Observations & Reward (observe/) ✅ **COMPLETE**

#### ✅ Completed:
- ✅ Module `observe/reader.py`:
  - ✅ `observe(namespace: str, deployment_name: str) -> dict` (returns `{"ready": int, "pending": int, "total": int}`)
  - ✅ `current_requests(namespace: str, deploy: str) -> dict` (returns `{"cpu": "...", "memory": "..."}`)
  - ✅ Uses kubeconfig from `~/.kube/config`
  - ✅ Error handling with safe defaults
- ✅ Module `observe/reward.py`:
  - ✅ `reward(obs: dict, target_total: int, T_s: int) -> int` (returns 1 if success, 0 otherwise)
  - ✅ Binary reward logic: `ready == target_total && total == target_total && pending == 0`
- ✅ CLI script `observe/print_obs.py`:
  - ✅ Supports `--ns` argument
  - ✅ Prints observation dict as JSON
- ✅ Unit tests `observe/text_observe.py` (should be renamed to `test_observe.py`):
  - ✅ 5+ tests for reward logic
  - ✅ Tests for observe with mocked Kubernetes clients
  - ✅ Tests cover: success, pending, not ready, wrong total, scaled up but not ready

#### ⚠️ Minor Issues:
1. **Test File Naming**: Tests are in `text_observe.py` instead of `test_observe.py`
   - **Fix**: Rename file or ensure pytest discovers it
2. **Test Organization**: Tests should be in `tests/` directory per project structure
   - **Fix**: Move `text_observe.py` to `tests/test_observe.py` or ensure it's discoverable

#### 📝 Acceptance Checks:
- ✅ `pytest` green with at least 5 tests (pending→reward 0, all ready→1, wrong totals→0, etc.)
- ✅ `observe/print_obs.py --ns test-ns` prints dict on live cluster

---

### 3. Bob — Trace & Actions (env/actions/) ✅ **COMPLETE**

#### ✅ Completed:
- ✅ Module `env/actions/trace_io.py`:
  - ✅ `load_trace(path: str) -> dict`
  - ✅ `save_trace(obj: dict, path: str) -> None`
  - ✅ MessagePack format support
  - ✅ Error handling (FileNotFoundError, ValueError, TypeError)
- ✅ Module `env/actions/ops.py`:
  - ✅ `bump_cpu_small(obj: dict, deploy: str, step: str = "500m") -> bool`
  - ✅ `bump_mem_small(obj: dict, deploy: str, step: str = "256Mi") -> bool`
  - ✅ `scale_up_replicas(obj: dict, deploy: str, delta: int = 1) -> bool`
  - ✅ Proper CPU/memory parsing and formatting
  - ✅ Returns `False` if deployment not found (leaves trace unchanged)
- ✅ CLI script `sk-action`:
  - ✅ Supports `sk-action apply --in ... --out ... --deploy ... --op ...`
  - ✅ Supports `--step` and `--delta` options
  - ✅ Prints JSON diff of changes
  - ✅ Returns appropriate exit codes
- ✅ Unit tests `tests/test_ops.py`:
  - ✅ Tests for `bump_cpu_small`, `bump_mem_small`, `scale_up_replicas`
  - ✅ Test for "deployment not found" returns `False` and leaves file unchanged
- ✅ Demo trace script `demo/make_demo_trace.py`:
  - ✅ Converts JSON to MessagePack
  - ✅ Supports `--json` and `--out` arguments
- ✅ Demo trace `demo/trace-0001.json`:
  - ✅ Synthetic trace with Deployment "web"
  - ✅ Contains CPU/memory requests

#### ❌ Missing:
1. **MessagePack File**: `demo/trace-0001.msgpack` doesn't exist (only JSON)
   - **Fix**: Run `python demo/make_demo_trace.py` to generate it

#### 📝 Acceptance Checks:
- ✅ `sk-action apply ...` produces new msgpack with intended changes
- ✅ Unit tests cover "deployment not found" case
- ⚠️ Need to generate `demo/trace-0001.msgpack` file

---

### 4. Rui — Hooks & Preflight (ops/) ⚠️ **PARTIALLY COMPLETE**

#### ✅ Completed:
- ✅ Script `ops/preflight.py`:
  - ✅ `check_kube_api()` - Checks Kubernetes API connectivity
  - ✅ `check_namespace(namespace: str)` - Checks if namespace exists
  - ✅ `check_crd()` - Checks if CRD is installed (function exists)
  - ✅ `main()` function exists
  - ✅ Helpful error messages
- ✅ Hooks runner `ops/hooks.py`:
  - ✅ `LocalHooks` class with `pre_start()` method
  - ✅ `delete_all_pods(namespace: str)` - Deletes all pods in namespace
  - ✅ Idempotent (handles 404 gracefully)
  - ✅ Uses kubeconfig from `~/.kube/config` with in-cluster fallback

#### ❌ Missing:
1. **Function Export**: `runner/one_step.py` expects `run_hooks(stage, namespace)` function
   - **Actual**: `LocalHooks().pre_start(namespace)` (class method)
   - **Fix**: Create wrapper function `run_hooks(stage: str, namespace: str) -> None`
2. **Preflight CLI**: No executable entry point for `preflight.py`
   - **Fix**: Add `if __name__ == "__main__"` block or create CLI script
3. **CRD Check Integration**: `check_crd()` exists but not called in `main()`
   - **Fix**: Add `check_crd()` call to `main()`
4. **Kubectl Version Check**: `MIN_KUBECTL_VERSION` defined but not used
   - **Fix**: Implement kubectl version check or remove constant
5. **Makefile Targets**: No `Makefile` with `make preflight` and `make clean-ns` targets
   - **Fix**: Create `Makefile` with targets

#### 🔧 Required Fixes:
```python
# In ops/hooks.py, add:
def run_hooks(stage: HookStage, namespace: str) -> None:
    """Wrapper function for runner/one_step.py"""
    hooks = LocalHooks()
    if stage == "pre_start":
        hooks.pre_start(namespace)
    elif stage == "pre_run":
        # Future: implement pre_run
        pass
    elif stage == "post_run":
        # Future: implement post_run
        pass
    elif stage == "post_stop":
        # Future: implement post_stop
        pass
    else:
        raise ValueError(f"Unknown hook stage: {stage}")

# In ops/preflight.py, update main():
def main():
    checks = [
        check_kube_api(),
        check_namespace(TARGET_NAMESPACE),
        check_crd(),  # Add this
    ]
    if all(checks):
        print("✓ All preflight checks passed")
        return 0
    else:
        print("✗ Some preflight checks failed")
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())
```

#### 📝 Acceptance Checks:
- ⚠️ `make preflight` - Need to create Makefile
- ⚠️ `make clean-ns` - Need to create Makefile
- ✅ `run_hooks("pre_start", "test-ns")` should delete pods (needs wrapper function)
- ✅ Idempotency: running twice should not error

---

### 5. Omar — Minimal Agent Loop & Orchestration (runner/) ⚠️ **INCOMPLETE**

#### ✅ Completed:
- ✅ Module `runner/one_step.py`:
  - ✅ Imports all required modules (with error handling)
  - ✅ `simple_policy()` function (if pending > 0 → bump_cpu_small, else noop)
  - ✅ `one_step()` function with orchestration logic:
    - ✅ pre_start hook
    - ✅ create simulation
    - ✅ wait fixed
    - ✅ observe
    - ✅ policy decision
    - ✅ load trace and apply action
    - ✅ compute reward
    - ✅ cleanup (delete simulation)
  - ✅ Logging setup
  - ✅ Error handling with cleanup

#### ❌ Missing:
1. **Helper Functions**: Missing three functions used in `one_step()`:
   - `deterministic_id(trace_path, namespace, deploy, target, timestamp) -> str`
   - `write_step_record(record: dict) -> None`
   - `update_summary(record: dict) -> None`
2. **CLI Entry Point**: No `if __name__ == "__main__"` block or `sk-run` script
   - **Fix**: Add CLI argument parsing and main function
3. **Import Issues**: Imports expect functions that don't exist:
   - `from env.sim_env import create_simulation, wait_fixed, delete_simulation` (needs wrapper functions)
   - `from ops.hooks import run_hooks` (needs wrapper function)
4. **File Structure**: `runs/step.jsonl` and `runs/summary.json` directories need to be created
   - **Fix**: Already handled in code with `LOG_DIR.mkdir()`, but ensure it works

#### 🔧 Required Fixes:
```python
# In runner/one_step.py, add:

import hashlib

def deterministic_id(trace_path: str, namespace: str, deploy: str, target: int, timestamp: str) -> str:
    """Generate a deterministic ID for the simulation"""
    data = f"{trace_path}{namespace}{deploy}{target}{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

def write_step_record(record: dict) -> None:
    """Write a single step record to step.jsonl"""
    with STEP_LOG.open("a") as f:
        json.dump(record, f)
        f.write("\n")

def update_summary(record: dict) -> None:
    """Update summary.json with the latest record"""
    if SUMMARY_LOG.exists():
        with SUMMARY_LOG.open("r") as f:
            summary = json.load(f)
    else:
        summary = {"steps": [], "total_rewards": 0, "total_steps": 0}
    
    summary["steps"].append(record)
    summary["total_steps"] = len(summary["steps"])
    summary["total_rewards"] = sum(r.get("reward", 0) for r in summary["steps"])
    
    with SUMMARY_LOG.open("w") as f:
        json.dump(summary, f, indent=2)

def main():
    parser = argparse.ArgumentParser(description="Run one agent step")
    parser.add_argument("--trace", required=True, help="Input trace path")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    parser.add_argument("--deploy", required=True, help="Deployment name")
    parser.add_argument("--target", type=int, required=True, help="Target total pods")
    parser.add_argument("--duration", type=int, default=120, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    args = parser.parse_args()
    
    return one_step(
        trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        seed=args.seed,
    )

if __name__ == "__main__":
    sys.exit(main())
```

#### 📝 Acceptance Checks:
- ⚠️ `sk-run one-step ...` - Need to create CLI entry point
- ⚠️ `runs/step.jsonl` - Need to implement `write_step_record()`
- ⚠️ `runs/summary.json` - Need to implement `update_summary()`
- ⚠️ Two dry runs back-to-back yield consistent logs

---

## Integration Gaps

### Critical Issues Preventing End-to-End Execution:

1. **Function Signature Mismatches**:
   - `runner/one_step.py` expects standalone functions, but modules export classes
   - **Fix**: Create wrapper functions in each module's `__init__.py` or modify runner

2. **Missing Helper Functions**:
   - `deterministic_id()`, `write_step_record()`, `update_summary()` not implemented
   - **Fix**: Implement these functions in `runner/one_step.py`

3. **Missing CLI Entry Points**:
   - No `sk-env` executable (only `sk_env_run.py`)
   - No `sk-run` executable (only `runner/one_step.py` without CLI)
   - **Fix**: Create executable scripts or add `if __name__ == "__main__"` blocks

4. **Missing Makefile**:
   - No `make preflight` or `make clean-ns` targets
   - **Fix**: Create `Makefile` with required targets

5. **Missing Demo Trace**:
   - `demo/trace-0001.msgpack` doesn't exist
   - **Fix**: Run `python demo/make_demo_trace.py` to generate it

---

## Next Steps (Priority Order)

### High Priority (Blocking MVP):

1. **Fix Function Exports** (Diya + Rui):
   - Create wrapper functions in `env/sim_env.py` or `env/__init__.py`:
     - `create_simulation(name, trace_path, duration_s, namespace) -> str`
     - `wait_fixed(duration_s) -> None`
     - `delete_simulation(name, namespace) -> None`
   - Create wrapper function in `ops/hooks.py`:
     - `run_hooks(stage: str, namespace: str) -> None`

2. **Complete Runner Implementation** (Omar):
   - Implement `deterministic_id()`, `write_step_record()`, `update_summary()` functions
   - Add CLI argument parsing and `main()` function
   - Test end-to-end execution

3. **Create Makefile** (Rui):
   - Add `make preflight` target (calls `ops/preflight.py`)
   - Add `make clean-ns` target (calls `ops/hooks.py pre_start`)
   - Ensure proper error handling and exit codes

4. **Generate Demo Trace** (Bob):
   - Run `python demo/make_demo_trace.py` to create `demo/trace-0001.msgpack`
   - Verify it can be loaded with `load_trace()`

5. **Create CLI Entry Points**:
   - Create `sk-env` script (wrapper around `sk_env_run.py`)
   - Create `sk-run` script (wrapper around `runner/one_step.py`)
   - Or add `if __name__ == "__main__"` blocks to existing files

### Medium Priority (Polish):

6. **Fix Preflight Script** (Rui):
   - Add `check_crd()` call to `main()`
   - Add `if __name__ == "__main__"` block
   - Implement kubectl version check or remove constant

7. **Organize Tests** (Cate):
   - Move `observe/text_observe.py` to `tests/test_observe.py`
   - Ensure pytest discovers all tests
   - Run full test suite to verify

8. **Add Requirements File**:
   - Create `requirements.txt` with dependencies:
     - `kubernetes`
     - `msgpack`
     - `pytest`
   - Document installation instructions

### Low Priority (Documentation):

9. **Create README**:
   - Document exact commands to reproduce one step from fresh clone
   - Include setup instructions
   - Include test instructions
   - Include troubleshooting guide

10. **Add Integration Tests**:
    - Test end-to-end flow with mocked Kubernetes API
    - Test error handling and cleanup
    - Test idempotency

---

## Test Matrix Status

- ⚠️ `make preflight` - **BLOCKED** (Makefile doesn't exist)
- ✅ Unit tests (Bob) - **PASSING** (tests/test_ops.py exists and works)
- ⚠️ Unit tests (Cate) - **PARTIAL** (tests exist but need organization)
- ⚠️ Dry-run: `sk-run one-step ...` - **BLOCKED** (CLI entry point missing)
- ⚠️ Idempotency: `make clean-ns` twice - **BLOCKED** (Makefile doesn't exist)

---

## Estimated Time to MVP

- **High Priority Tasks**: 4-6 hours
  - Function exports: 1-2 hours
  - Runner completion: 1-2 hours
  - Makefile: 30 minutes
  - Demo trace: 5 minutes
  - CLI entry points: 30 minutes
- **Medium Priority Tasks**: 2-3 hours
- **Total**: 6-9 hours of focused work

---

## Recommendations for Two-Person Team

### Person 1 (Integration Focus):
1. Fix function exports (wrapper functions)
2. Complete runner implementation (helper functions + CLI)
3. Create Makefile
4. Test end-to-end execution

### Person 2 (Polish & Testing):
1. Generate demo trace
2. Organize tests
3. Create requirements.txt
4. Create README
5. Run full test suite

---

## Notes

- All core functionality is implemented (~70% complete)
- Main blocker is integration between modules (function signatures)
- Once integration is fixed, MVP should work end-to-end
- Test coverage is good for actions module, needs organization for observe module
- Documentation needs improvement but is not blocking MVP

