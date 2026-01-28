"""
runner/one_step_2.py

A simpler "one reproducible agent step" runner:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> validate -> edit trace -> save -> reward -> log -> cleanup

Usage:
  python runner/one_step_2.py --trace demo/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 120
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Tuple

# If running as a script (not as a module), ensure project root is on sys.path
# so `from runner...` imports work.
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ops.hooks import run_hooks
from env import create_simulation, wait_fixed, delete_simulation
from observe.reader import observe
from observe.reward import reward as compute_reward
from env.actions.trace_io import load_trace, save_trace
from env.actions.ops import bump_cpu_small, bump_mem_small, scale_up_replicas
from runner.policies import get_policy
from runner.safeguards import validate_action

# ---- Logging setup ----
LOG_DIR = Path("runs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STEP_LOG = LOG_DIR / "step.jsonl"
SUMMARY_LOG = LOG_DIR / "summary.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("one_step_2")


def deterministic_id(trace_path: str, namespace: str, deploy: str, target: int, timestamp: str) -> str:
    data = f"{trace_path}{namespace}{deploy}{target}{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]


def write_step_record(record: dict) -> None:
    with STEP_LOG.open("a") as f:
        json.dump(record, f)
        f.write("\n")


def update_summary(record: dict) -> None:
    if SUMMARY_LOG.exists():
        summary = json.loads(SUMMARY_LOG.read_text())
    else:
        summary = {"steps": [], "total_rewards": 0, "total_steps": 0}

    summary["steps"].append(record)
    summary["total_steps"] = len(summary["steps"])
    summary["total_rewards"] = sum(r.get("reward", 0) for r in summary["steps"])

    SUMMARY_LOG.write_text(json.dumps(summary, indent=2))


def _extract_current_state(trace: Dict[str, Any], deploy: str) -> Dict[str, Any]:
    """
    Extract current CPU, memory, and replicas for a deployment from the trace dict.

    This matches your existing logic: walk trace["events"][...]["applied_objs"]
    and find the last/first matching Deployment object.
    """
    current = {"cpu": "0m", "memory": "0Mi", "replicas": 0}

    events = trace.get("events", [])
    for event in events:
        for obj in event.get("applied_objs", []):
            if obj.get("kind") != "Deployment":
                continue
            if obj.get("metadata", {}).get("name") != deploy:
                continue

            spec = obj.get("spec", {})
            current["replicas"] = spec.get("replicas", 0)

            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            if containers:
                requests = containers[0].get("resources", {}).get("requests", {})
                current["cpu"] = requests.get("cpu", "0m")
                current["memory"] = requests.get("memory", "0Mi")

            return current

    return current


def apply_action_to_trace(trace_path: str, action: dict, deploy: str, output_path: str) -> Tuple[str, dict]:
    """
    Load trace once -> validate action -> apply -> save.

    Returns (output_path, info_dict).
    """
    trace = load_trace(trace_path)
    current_state = _extract_current_state(trace, deploy)

    is_valid, error_msg = validate_action(action, current_state=current_state)
    if not is_valid:
        logger.warning(f"Action blocked by safeguards: {error_msg}")
        save_trace(trace, output_path)
        return output_path, {
            "changed": False,
            "action_type": action.get("type"),
            "blocked": True,
            "error": error_msg,
        }

    action_type = action.get("type", "noop")
    changed = False

    if action_type == "noop":
        pass
    elif action_type == "bump_cpu_small":
        changed = bump_cpu_small(trace, deploy, step=action.get("step", "500m"))
    elif action_type == "bump_mem_small":
        changed = bump_mem_small(trace, deploy, step=action.get("step", "256Mi"))
    elif action_type == "scale_up_replicas":
        changed = scale_up_replicas(trace, deploy, delta=action.get("delta", 1))
    else:
        raise ValueError(f"Unknown action type: {action_type}")

    save_trace(trace, output_path)
    return output_path, {"changed": changed, "action_type": action_type, "blocked": False}


def one_step(
    trace_path: str,
    namespace: str,
    deploy: str,
    target: int,
    duration: int,
    seed: int = 0,
    policy_name: str = "heuristic",
) -> dict:
    random.seed(seed)

    timestamp = datetime.utcnow().isoformat() + "Z"
    trace_path = str(trace_path)

    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_trace_path = str(tmp_dir / "trace-next.msgpack")

    sim_name = f"diag-{deterministic_id(trace_path, namespace, deploy, target, timestamp)}"
    logger.info(
        f"Starting one_step: sim_name={sim_name} ns={namespace} trace={trace_path} "
        f"deploy={deploy} target={target} duration={duration} policy={policy_name}"
    )

    sim_uid = None
    start_time = time.time()
    record = None

    try:
        logger.info("Running pre_start hooks...")
        run_hooks("pre_start", namespace)

        logger.info("Creating simulation CR...")
        sim_uid = create_simulation(
            name=sim_name,
            trace_path=trace_path,
            duration_s=duration,
            namespace=namespace,
        )
        logger.info(f"Created simulation uid={sim_uid}")

        logger.info(f"Waiting {duration}s...")
        wait_fixed(duration)

        logger.info("Observing cluster state...")
        obs = observe(namespace, deploy)
        logger.info(f"Observation: {obs}")

        policy_fn = get_policy(policy_name)
        action = policy_fn(obs=obs, deploy=deploy)
        logger.info(f"Policy '{policy_name}' chose action: {action}")

        logger.info("Applying action to trace...")
        out_trace_path, action_info = apply_action_to_trace(trace_path, action, deploy, out_trace_path)

        r = compute_reward(obs, target_total=target, T_s=duration)
        logger.info(f"Reward: {r}")

        record = {
            "timestamp": timestamp,
            "sim_name": sim_name,
            "sim_uid": sim_uid,
            "namespace": namespace,
            "trace_in": trace_path,
            "trace_out": out_trace_path,
            "obs": obs,
            "action": action,
            "action_info": action_info,
            "reward": int(r),
            "duration_s": duration,
            "seed": seed,
            "policy": policy_name,
        }
        write_step_record(record)
        update_summary(record)

        logger.info(
            f"Step Summary: action={action.get('type')} reward={r} changed={action_info.get('changed')}\n"
            f"Obs: ready={obs.get('ready')} pending={obs.get('pending')} total={obs.get('total')}"
        )

    finally:
        if sim_uid:
            try:
                logger.info("Cleaning up simulation CR...")
                delete_simulation(sim_name, namespace)
            except Exception as e:
                logger.warning(f"Failed to delete simulation {sim_name}: {e}")

    elapsed = time.time() - start_time
    logger.info(f"one_step finished in {elapsed:.2f}s")

    return {"status": 0, "elapsed_s": elapsed, "record": record}


def main() -> int:
    p = argparse.ArgumentParser(description="Run one agent step (simplified)")
    p.add_argument("--trace", required=True, help="Input trace path")
    p.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    p.add_argument("--deploy", required=True, help="Deployment name")
    p.add_argument("--target", type=int, required=True, help="Target total pods")
    p.add_argument("--duration", type=int, default=120, help="Duration in seconds")
    p.add_argument("--seed", type=int, default=0, help="Random seed")
    p.add_argument("--policy", type=str, default="heuristic", help="Policy to use (registry key)")

    args = p.parse_args()
    one_step(
        trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        seed=args.seed,
        policy_name=args.policy,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())