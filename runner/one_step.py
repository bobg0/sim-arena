"""
runner/one_step.py

Orchestrate one reproducible agent step:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> save trace -> reward -> log

Usage:
  python runner/one_step.py --trace demo/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 120
"""
import sys
from pathlib import Path

# Add project root to Python path so imports work
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
import hashlib
import random

# ---- Try importing project modules (fail fast with helpful message) ----
try:
    from ops.hooks import run_hooks
except Exception as e:
    print("ERROR: failed to import ops.hooks.run_hooks. Make sure /ops is on PYTHONPATH and file exists.", file=sys.stderr)
    raise

try:
    from env import create_simulation, wait_fixed, delete_simulation
except Exception as e:
    print("ERROR: failed to import env functions. Make sure /env/__init__.py exists.", file=sys.stderr)
    raise

try:
    from observe.reader import observe
    from observe.reward import reward as compute_reward
except Exception as e:
    print("ERROR: failed to import observe.reader or observe.reward. Make sure /observe exists.", file=sys.stderr)
    raise

try:
    from env.actions.trace_io import load_trace, save_trace
except Exception as e:
    print("ERROR: failed to import actions.trace_io. Make sure /actions exists.", file=sys.stderr)
    raise

try:
    from runner.action_applier import apply_action_from_policy
except Exception as e:
    print("ERROR: failed to import action_applier. Make sure runner/action_applier.py exists.", file=sys.stderr)
    raise

# ---- Logging setup ----
LOG_DIR = Path("runs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STEP_LOG = LOG_DIR / "step.jsonl"
SUMMARY_LOG = LOG_DIR / "summary.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("one_step")

# ---- Helper functions ----

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

# ---- Policy (heuristic) ----
def simple_policy(obs: dict, deploy: str):
    """
    Heuristic policy:
      - if pending > 0: request bump_cpu_small
      - else: noop
    Returns: dict describing action: {"type": "bump_cpu_small", "deploy": deploy} or {"type": "noop"}
    """
    pending = int(obs.get("pending", 0))
    # if pending > 0:
    return {"type": "bump_cpu_small", "deploy": deploy}
    # return {"type": "noop"}
# pending because have too much cpu, 
# bumping cpu will still make pending 
# probably neeed to reduce cpu for the pending to actually 
# ---- Main orchestration ----
def one_step(trace_path: str, namespace: str, deploy: str, target: int, duration: int, seed: int = 0):
    random.seed(seed)
    
    timestamp = datetime.utcnow().isoformat() + "Z"
    trace_path = str(trace_path)
    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_trace_path = str(tmp_dir / "trace-next.msgpack")
    
    sim_name = f"diag-{deterministic_id(trace_path, namespace, deploy, target, timestamp)}"
    logger.info(f"Starting one_step run: sim_name={sim_name}, ns={namespace}, trace={trace_path}, deploy={deploy}, target={target}, duration={duration}")

    sim_uid = None
    start_time = time.time()

    try:
        # 1) pre_start hook
        logger.info("Running pre_start hooks...")
        run_hooks("pre_start", namespace)
        logger.info("pre_start hooks completed.")
        
        # 2) create simulation CR
        logger.info("Creating simulation CR...")
        sim_uid = create_simulation(name=sim_name, trace_path=trace_path, duration_s=duration, namespace=namespace)
        logger.info(f"Created simulation (uid={sim_uid}).")
        
        # 3) wait fixed (block until observation time)
        logger.info(f"Waiting fixed duration: {duration}s ...")
        wait_fixed(duration)
        logger.info("Wait complete, proceeding to observe.")
        
        # 4) observe cluster state
        logger.info("Observing cluster state...")
        obs = observe(namespace, deploy)
        logger.info(f"Observation: {obs}")
        
        # 5) policy decision
        action = simple_policy(obs, deploy)
        logger.info(f"Policy chose action: {action}")
        
        # 6) Apply action to trace (using action_applier module)
        logger.info(f"Applying action from policy: {action}")
        action_info = None
        try:
            out_trace_path, action_info = apply_action_from_policy(
                trace_path=trace_path,
                action=action,
                deploy=deploy,
                output_path=out_trace_path,
            )
            trace_changed = action_info.get("changed", False)
            logger.info(f"Action application complete. Changed: {trace_changed}")
        except Exception as e:
            logger.error(f"Failed to apply action to trace {trace_path}: {e}")
            raise
        
        # 7) compute reward
        r = compute_reward(obs, target_total=target, T_s=duration)
        logger.info(f"Reward computed: {r}")
        
        # 8) write logs: step.jsonl and summary.json
        record = {
            "timestamp": timestamp,
            "sim_name": sim_name,
            "sim_uid": sim_uid,
            "namespace": namespace,
            "trace_in": trace_path,
            "trace_out": out_trace_path,
            "obs": obs,
            "action": action,
            "action_info": action_info if action_info else {},
            "reward": int(r),
            "duration_s": duration,
            "seed": seed,
        }
        write_step_record(record)
        update_summary(record)
        
        # Print summary of step results
        logger.info("=" * 60)
        logger.info(f"Step Summary: action={action.get('type')}, reward={r}, changed={trace_changed}")
        logger.info(f"Observation: ready={obs.get('ready')}, pending={obs.get('pending')}, total={obs.get('total')}")
        logger.info("=" * 60)
    
    finally:
        # Attempt best-effort cleanup: delete simulation CR if function available
        if sim_uid:
            try:
                logger.info("Cleaning up: deleting simulation CR...")
                delete_simulation(sim_name, namespace)
                logger.info("Simulation deleted.")
            except Exception as e:
                logger.warning(f"Failed to delete simulation {sim_name}: {e}")

    elapsed = time.time() - start_time
    logger.info(f"one_step completed in {elapsed:.2f}s")
    return 0

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

## CALL CATES OBSERVE FUNCTION

# KUBERNETES NAME SPACE AND TARGET TOTAL NUMBER OF PODS