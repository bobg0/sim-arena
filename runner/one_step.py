"""
runner/one_step.py

Orchestrate one reproducible agent step:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> save trace -> reward -> log

Usage:
  python runner/one_step.py --trace demo/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 120
"""
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
    from env.actions.ops import bump_cpu_small
except Exception as e:
    print("ERROR: failed to import actions.trace_io or actions.ops. Make sure /actions exists.", file=sys.stderr)
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

# ---- Policy (heuristic) ----
def simple_policy(obs: dict, deploy: str):
    """
    Heuristic policy:
      - if pending > 0: request bump_cpu_small
      - else: noop
    Returns: dict describing action: {"type": "bump_cpu_small", "deploy": deploy} or {"type": "noop"}
    """
    pending = int(obs.get("pending", 0))
    if pending > 0:
        return {"type": "bump_cpu_small", "deploy": deploy}
    return {"type": "noop"}

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
        
        # 6) Load trace and apply action (if any)
        trace_obj = None
        trace_changed = False
        try:
            trace_obj = load_trace(trace_path)
        except Exception as e:
            logger.error(f"Failed to load trace {trace_path}: {e}")
            raise
        
        if action["type"] == "bump_cpu_small":
            logger.info("Applying bump_cpu_small to trace...")
            ok = bump_cpu_small(trace_obj, deploy, step="500m")
            if ok:
                trace_changed = True
                save_trace(trace_obj, out_trace_path)
                logger.info(f"Saved modified trace to {out_trace_path}")
            else:
                logger.warning("bump_cpu_small returned False (deployment not found or no-op). Saving original trace as out.")
                save_trace(trace_obj, out_trace_path)
        else:
            # noop - still write out a copy to .tmp
            logger.info("No-op chosen; writing copy of trace to out path.")
            save_trace(trace_obj, out_trace_path)
        
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
            "reward": int(r),
            "duration_s": duration,
            "seed": seed,
        }
        write_step_record(record)
        update_summary(record)
    
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

## CALL CATES OBSERVE FUNCTION

# KUBERNETES NAME SPACE AND TARGET TOTAL NUMBER OF PODS