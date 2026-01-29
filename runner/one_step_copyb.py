"""
runner/one_step_copyb.py

One reproducible agent step:
pre_start -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> reward -> log -> cleanup
"""

import argparse
import hashlib
import json
import logging
import random
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure project root is on sys.path for local imports
_SCRIPT_DIR = Path(__file__).parent.resolve()
_PROJECT_ROOT = _SCRIPT_DIR.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from ops.hooks import run_hooks
from env import wait_fixed, delete_simulation
from env.sim_env import SimEnv
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
logger = logging.getLogger("one_step_copyb")


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


def _extract_current_state(trace: dict, deploy: str) -> dict:
    current = {"cpu": "0m", "memory": "0Mi", "replicas": 0}
    for event in trace.get("events", []):
        for obj in event.get("applied_objs", []):
            if obj.get("kind") == "Deployment" and obj.get("metadata", {}).get("name") == deploy:
                spec = obj.get("spec", {})
                current["replicas"] = spec.get("replicas", 0)
                containers = spec.get("template", {}).get("spec", {}).get("containers", [])
                if containers:
                    requests = containers[0].get("resources", {}).get("requests", {})
                    current["cpu"] = requests.get("cpu", "0m")
                    current["memory"] = requests.get("memory", "0Mi")
                return current
    return current


def apply_action_to_trace(trace_path: str, action: dict, deploy: str, output_path: str) -> tuple[str, dict]:
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


def _log_trace_version(trace_path: str) -> None:
    if trace_path.startswith("file://"):
        logger.info(f"Trace version: unknown (remote path {trace_path})")
        return
    trace = load_trace(trace_path)
    version = trace.get("version")
    logger.info(f"Trace version: {version}")


def one_step(
    trace_path: str,
    namespace: str,
    deploy: str,
    target: int,
    duration: int,
    seed: int = 0,
    policy_name: str = "heuristic",
    driver_image: str = "quay.io/appliedcomputing/sk-driver:v2.4.1",
) -> dict:
    random.seed(seed)

    timestamp = datetime.utcnow().isoformat() + "Z"
    local_trace_path = str(trace_path)

    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_trace_path = str(tmp_dir / "trace-next.msgpack")
    _log_trace_version(local_trace_path)

    if not local_trace_path.startswith(("file://", "http://", "https://")):
        trace_filename = Path(local_trace_path).name
        cluster_trace_path = f"file:///data/{trace_filename}"
    else:
        cluster_trace_path = local_trace_path

    sim_name = f"diag-{deterministic_id(local_trace_path, namespace, deploy, target, timestamp)}"
    logger.info(
        "Starting one_step: sim_name=%s ns=%s trace=%s deploy=%s target=%s duration=%s policy=%s driver_image=%s",
        sim_name,
        namespace,
        cluster_trace_path,
        deploy,
        target,
        duration,
        policy_name,
        driver_image,
    )

    sim_uid = None
    start_time = time.time()
    record = None

    try:
        logger.info("Running pre_start hooks...")
        run_hooks("pre_start", namespace)

        logger.info("Creating simulation CR...")
        sim_env = SimEnv()
        sim_uid = sim_env.create(
            name=sim_name,
            trace_path=cluster_trace_path,
            namespace=namespace,
            duration_s=duration,
            driver_image=driver_image,
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
        if local_trace_path.startswith("file://"):
            logger.warning("Skipping trace edit (remote trace path).")
            action_info = {"changed": False, "action_type": action.get("type"), "blocked": False, "skipped": True}
            out_trace_path = local_trace_path
        else:
            out_trace_path, action_info = apply_action_to_trace(local_trace_path, action, deploy, out_trace_path)

        r = compute_reward(obs, target_total=target, T_s=duration)
        logger.info(f"Reward: {r}")

        record = {
            "timestamp": timestamp,
            "sim_name": sim_name,
            "sim_uid": sim_uid,
            "namespace": namespace,
            "trace_in": local_trace_path,
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
            "Step Summary: action=%s reward=%s changed=%s obs_ready=%s obs_pending=%s obs_total=%s",
            action.get("type"),
            r,
            action_info.get("changed"),
            obs.get("ready"),
            obs.get("pending"),
            obs.get("total"),
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
    p = argparse.ArgumentParser(description="Run one agent step (copyb)")
    p.add_argument("--trace", required=True, help="Input trace path")
    p.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    p.add_argument("--deploy", required=True, help="Deployment name")
    p.add_argument("--target", type=int, required=True, help="Target total pods")
    p.add_argument("--duration", type=int, default=120, help="Duration in seconds")
    p.add_argument("--seed", type=int, default=0, help="Random seed")
    p.add_argument("--policy", type=str, default="heuristic", help="Policy to use (registry key)")
    p.add_argument("--driver-image", type=str, default="quay.io/appliedcomputing/sk-driver:v2.4.1", help="SimKube driver image")

    args = p.parse_args()
    one_step(
        trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        seed=args.seed,
        policy_name=args.policy,
        driver_image=args.driver_image,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())