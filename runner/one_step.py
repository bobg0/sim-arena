"""
runner/one_step.py

Orchestrate one reproducible agent step:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> save trace -> reward -> log

Usage:
  # Basic example with epsilon-greedy agent
  python runner/one_step.py --trace demo/trace-0001.msgpack --ns virtual-default --deploy web --target 3 --duration 60 --log-level DEBUG

  # With shaped reward for better RL training
  python runner/one_step.py --trace demo/trace-scaling-v2.msgpack --ns virtual-default --deploy web --target 3 --duration 60 --reward shaped
"""
import argparse
import hashlib
import json
import logging
import random
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# Add project root to Python path (must be before local imports)
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.agent import Agent, AgentType

# Import project modules
from ops.hooks import run_hooks
from env import create_simulation, wait_fixed, delete_simulation
from observe.reader import observe, current_requests, add_obs_noise
from observe.reward import get_reward
from env.actions.trace_io import load_trace, save_trace
from env.actions.ops import (
    bump_cpu_small,
    bump_mem_small,
    reduce_cpu_small,
    reduce_mem_small,
    scale_up_replicas,
    scale_down_replicas,
)
from runner.safeguards import validate_action
from runner.policies import get_policy

# ---- Logging setup ----
LOG_DIR = Path("runs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STEP_LOG = LOG_DIR / "step.jsonl"
SUMMARY_LOG = LOG_DIR / "summary.json"

logger = logging.getLogger("one_step")

def wait_for_driver_ready(sim_name: str, timeout: int = 60) -> bool:
    """Polls Kubernetes until the SimKube driver pod is actively Running."""
    import subprocess

    job_label = f"job-name=sk-{sim_name}-driver"
    logger.info(f"Waiting for driver pod ({job_label}) to start to eliminate cluster lag...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        try:
            # -A searches all namespaces so we definitely find it
            cmd = [
                "kubectl", "get", "pods", "-A", 
                "-l", job_label, 
                "-o", "jsonpath={.items[0].status.phase}"
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            phase = result.stdout.strip()
            
            if phase == "Running":
                elapsed = time.time() - start_time
                logger.debug(f"Driver pod is Running! (Scheduling lag handled: {elapsed:.1f}s)")
                return True
            elif phase in ["Succeeded", "Failed"]:
                return True
        except Exception:
            pass # Ignore temporary kubectl failures
        
        time.sleep(2)
        
    logger.warning(f"Driver pod didn't enter Running state within {timeout}s buffer. Proceeding anyway.")
    return False

def _get_node_data_dir(kind_cluster: str) -> Path:
    """Path where trace files must be placed for SimKube to read them at file:///data/"""
    return Path.home() / ".local" / "kind-node-data" / kind_cluster

# ---- Helper function to extract current resource state from trace ----
def _extract_current_state(trace: list, deploy: str) -> dict:
    current_state = {"cpu": "0m", "memory": "0Mi", "replicas": 0}
    events = trace.get("events", [])
    for event in events:
        applied_objs = event.get("applied_objs", [])
        for obj in applied_objs:
            if obj.get("kind") == "Deployment" and obj.get("metadata", {}).get("name") == deploy:
                spec = obj.get("spec", {})
                template = spec.get("template", {})
                containers = template.get("spec", {}).get("containers", [])
                current_state["replicas"] = spec.get("replicas", 0)
                if containers:
                    resources = containers[0].get("resources", {})
                    requests = resources.get("requests", {})
                    current_state["cpu"] = requests.get("cpu", "0m")
                    current_state["memory"] = requests.get("memory", "0Mi")
                return current_state
    return current_state

# ---- Action application ----
def apply_action(trace_path: str, action: dict, deploy: str, output_path: str) -> tuple[str, dict]:
    trace = load_trace(trace_path)
    current_state = _extract_current_state(trace, deploy)
    
    is_valid, error_msg = validate_action(action, current_state=current_state)
    if not is_valid:
        logger.warning(f"⚠️  Action blocked by safeguards: {error_msg}")
        save_trace(trace, output_path)
        return output_path, {"changed": False, "action_type": action.get("type"), "blocked": True, "error": error_msg}
    
    action_type = action.get("type", "noop")
    changed = False
    
    if action_type == "noop":
        save_trace(trace, output_path)
    elif action_type == "bump_cpu_small":
        changed = bump_cpu_small(trace, deploy, step=action.get("step", "500m"))
        save_trace(trace, output_path)
    elif action_type == "bump_mem_small":
        changed = bump_mem_small(trace, deploy, step=action.get("step", "256Mi"))
        save_trace(trace, output_path)
    elif action_type == "reduce_cpu_small":
        changed = reduce_cpu_small(trace, deploy, step=action.get("step", "500m"))
        save_trace(trace, output_path)
    elif action_type == "reduce_mem_small":
        changed = reduce_mem_small(trace, deploy, step=action.get("step", "256Mi"))
        save_trace(trace, output_path)
    elif action_type == "scale_up_replicas":
        changed = scale_up_replicas(trace, deploy, delta=action.get("delta", 1))
        save_trace(trace, output_path)
    elif action_type == "scale_down_replicas":
        changed = scale_down_replicas(trace, deploy, delta=action.get("delta", 1))
        save_trace(trace, output_path)
    else:
        raise ValueError(f"Unknown action type: {action_type}")
    
    info = {"changed": changed, "action_type": action_type, "blocked": False}
    return output_path, info

# ---- Helper functions ----
def deterministic_id(trace_path: str, namespace: str, deploy: str, target: int, timestamp: str) -> str:
    data = f"{trace_path}{namespace}{deploy}{target}{timestamp}"
    return hashlib.md5(data.encode()).hexdigest()[:8]

def write_step_record(record: dict) -> None:
    with STEP_LOG.open("a") as f:
        json.dump(record, f)
        f.write("\n")

def update_summary(record: dict) -> None:
    if SUMMARY_LOG.exists():
        try:
            with SUMMARY_LOG.open("r") as f:
                summary = json.load(f)
        except json.JSONDecodeError:
            logger.warning(f"⚠️ Corrupted summary log found at {SUMMARY_LOG}. Starting fresh.")
            summary = {"steps": [], "total_rewards": 0, "total_steps": 0}
    else:
        summary = {"steps": [], "total_rewards": 0, "total_steps": 0}
    
    summary["steps"].append(record)
    summary["total_steps"] = len(summary["steps"])
    summary["total_rewards"] = sum(r.get("reward", 0) for r in summary["steps"])
    
    with SUMMARY_LOG.open("w") as f:
        json.dump(summary, f, indent=2)
 
# ---- Main orchestration ----
def one_step(
    trace_path: str,
    namespace: str,
    deploy: str,
    target: int,
    duration: int,
    seed: int = 0,
    agent_name: str = "heuristic",
    reward_name: str = "shaped",
    agent=None,
    step_idx: int = 0,
    reward_kwargs: Optional[dict] = None,
    obs_noise_scale: float = 0.0,
    reward_fn=None,
):
    random.seed(seed)
    
    timestamp = datetime.now(timezone.utc).isoformat() 
    local_trace_path = str(trace_path)
    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    sim_id = deterministic_id(local_trace_path, namespace, deploy, target, timestamp)
    sim_name = f"diag-{sim_id}"
    out_trace_path = str(tmp_dir / f"trace-next-{sim_id}.msgpack")

    trace_filename = Path(local_trace_path).name
    cluster_trace_path = f"file:///data/{trace_filename}"
    sim_name = f"diag-{deterministic_id(local_trace_path, namespace, deploy, target, timestamp)}"
    virtual_namespace = "virtual-default"
    
    logger.info(f"Starting one_step run: sim_name={sim_name}, ns={namespace} (virtual={virtual_namespace}), trace={cluster_trace_path}, deploy={deploy}, target={target}, duration={duration}, agent={agent_name}, reward={reward_name}")

    sim_uid = None
    start_time = time.time()
    record = None
    trace_changed = False

    try:
        # 1) pre_start hook
        # NOTE: Clean up virtual namespace where SimKube creates pods.
        # Pass deploy so we wait for previous deployment cleanup (fixes step 5 404).
        logger.debug(f"Running pre_start hooks in {virtual_namespace}...")
        run_hooks("pre_start", virtual_namespace, deploy=deploy)
        logger.debug("pre_start hooks completed.")

        # 1.5) Copy the input trace to the kind node data path (mounted at /data in the node)
        # isengard mounts ~/.local/kind-node-data/<namespace> -> /data in the kind worker
        node_data_dir = _get_node_data_dir(namespace)
        node_data_dir.mkdir(parents=True, exist_ok=True)
        dest_trace = node_data_dir / trace_filename
        shutil.copy2(local_trace_path, dest_trace)
        logger.debug(f"Copied input trace to {dest_trace} (accessible at file:///data/{trace_filename})")
        
        # 2) create simulation CR
        logger.debug("Creating simulation CR...")
        sim_uid = create_simulation(name=sim_name, trace_path=cluster_trace_path, duration_s=duration, namespace=namespace)

        # 2.5) Synchronize timer with the driver pod
        wait_for_driver_ready(sim_name)
        
        # 3) wait fixed
        logger.info(f"Waiting fixed duration: {duration}s ...")
        wait_fixed(duration)
        
        # 4) observe cluster state
        logger.debug(f"Observing cluster state in {virtual_namespace}...")
        obs = None

        # Smart Polling: 16-second grace period for the Kubernetes API to sync
        for _ in range(8): 
            obs = observe(virtual_namespace, deploy)
            if obs and obs.get("total", 0) > 0:
                break
            time.sleep(2)


        if obs_noise_scale > 0:
            obs = add_obs_noise(obs, obs_noise_scale, rng=random)
        resources = current_requests(virtual_namespace, deploy)
        logger.info(f"Observation: {obs}")
        logger.info(f"Current requests: {resources}")

        # Safely parse CPU to millicores (translates "1" -> 1000)
        cpu_raw = str(resources.get("cpu", "0m"))
        cpu_m = int(cpu_raw[:-1]) if cpu_raw.endswith("m") else int(float(cpu_raw) * 1000)

        # Safely parse Memory to MiB (translates "1Gi" -> 1024)
        mem_raw = str(resources.get("memory", "0Mi"))
        if mem_raw.endswith("Gi"):
            mem_mi = int(float(mem_raw[:-2]) * 1024)
        elif mem_raw.endswith("Mi"):
            mem_mi = int(mem_raw[:-2])
        else:
            # Fallback for raw bytes or unknown units
            mem_mi = int("".join(filter(str.isdigit, mem_raw)) or 0)

        distance = target - obs.get("total", 0)
        total = obs.get("total", 0)
        replicas = resources.get("replicas", total)
        try:
            replicas = int(replicas) if isinstance(replicas, (int, float)) else int(str(replicas))
        except (ValueError, TypeError):
            replicas = total

        dqn_state = [
            cpu_m / 4000,
            mem_mi / 4096,
            obs.get("pending", 0) / 5,
            distance / 5,
            min(1.0, replicas / 8),
        ]

        # 4b) At target: no action taken, episode terminates (trace unchanged)
        ready = obs.get("ready", 0)
        pending = obs.get("pending", 0)
        at_target = (ready == target and total == target and pending == 0)

        ACTION_SPACE = {
            0: {"type": "noop"},
            1: {"type": "bump_cpu_small", "step": "500m"},
            2: {"type": "bump_mem_small", "step": "256Mi"},
            3: {"type": "scale_up_replicas", "delta": 1},
            4: {"type": "reduce_cpu_small", "step": "500m"},
            5: {"type": "reduce_mem_small", "step": "256Mi"},
            6: {"type": "scale_down_replicas", "delta": 1},
        }

        action_idx = None
        if at_target:
            action = ACTION_SPACE[0]
            action_idx = 0
            action_info = {"changed": False, "blocked": False}
            logger.info("Target reached: skipping action (no modification)")
        elif agent_name == "greedy" and agent is not None:
            action_idx = agent.act()
            action = ACTION_SPACE.get(action_idx, {"type": "noop"})
            logger.debug(f"Agent '{agent_name}' chose action index: {action_idx}")
        elif agent_name == "dqn" and agent is not None:
            action_idx = agent.act(dqn_state)
            action = ACTION_SPACE.get(action_idx, {"type": "noop"})
            logger.debug(f"Agent '{agent_name}' chose action index: {action_idx}")
        else:
            policy_fn = get_policy(agent_name)
            action = policy_fn(obs=obs, deploy=deploy)
            logger.debug(f"Policy '{agent_name}' chose action: {action}")

        # 6) Apply action to trace (when at_target, apply noop → trace unchanged)
        logger.debug(f"Applying action: {action}")
        out_trace_path, action_info = apply_action(local_trace_path, action, deploy, out_trace_path)
        trace_changed = action_info.get("changed", False)
        
        # 6b) Copy output trace to the kind node data path (for next step)
        out_trace_name = Path(out_trace_path).name
        dest_out = node_data_dir / out_trace_name
        shutil.copy2(out_trace_path, dest_out)
        logger.debug(f"Copied output trace to {dest_out}")
        
        # 7) Compute reward (use reward_shaped for continuous RL feedback)
        rfn = reward_fn if reward_fn is not None else get_reward(
            reward_name,
            **(reward_kwargs or {}),
        )
        r = rfn(
            obs=obs,
            target_total=target,
            T_s=duration,
            resources=resources,
            step_idx=step_idx,
            action_info=action_info if action_info else {},
        )
        logger.debug(f"Reward computed: {r}")
        
        # 8) write logs
        record = {
            "timestamp": timestamp,
            "sim_name": sim_name,
            "sim_uid": sim_uid,
            "namespace": virtual_namespace,
            "trace_in": local_trace_path,
            "trace_out": out_trace_path,
            "obs": obs,
            "dqn_state": dqn_state,
            "action_idx": action_idx,
            "action": action,
            "action_info": action_info if action_info else {},
            "reward": float(r),
            "duration_s": duration,
            "seed": seed,
            "at_target": at_target,
        }
        write_step_record(record)
        update_summary(record)
        
        # Step summary pushed to debug to prevent flooding multi_step logs
        logger.info(f"Step Summary: action={action.get('type')}, reward={r}, changed={trace_changed}")
    finally:
        if sim_uid:
            try:
                logger.debug("Cleaning up: deleting simulation CR...")
                delete_simulation(sim_name, namespace)
            except Exception as e:
                logger.warning(f"Failed to delete simulation {sim_name}: {e}")

    elapsed = time.time() - start_time
    logger.debug(f"one_step completed in {elapsed:.2f}s")
    
    return {
        "status": 0,
        "elapsed_s": elapsed,
        "record": record
    }

def main():
    parser = argparse.ArgumentParser(description="Run one agent step")
    parser.add_argument("--trace", required=True, help="Input trace path")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    parser.add_argument("--deploy", required=True, help="Deployment name")
    parser.add_argument("--target", type=int, required=True, help="Target total pods")
    parser.add_argument("--duration", type=int, default=120, help="Duration in seconds")
    parser.add_argument("--seed", type=int, default=0, help="Random seed")
    parser.add_argument("--agent", type=str, default="greedy", help="Agent/policy: greedy, dqn, heuristic, scale_replicas, etc.")
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (base, shaped, max_punish)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set the logging level")

    args = parser.parse_args()
    
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    agent = None
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=7, epsilon=0.1)
    elif args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=5, n_actions=7)

    result = one_step(
        trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        seed=args.seed,
        agent_name=args.agent,
        reward_name=args.reward,
        agent=agent,
    )
    return result["status"]

if __name__ == "__main__":
    sys.exit(main())