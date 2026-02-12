"""
runner/one_step.py

Orchestrate one reproducible agent step:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> save trace -> reward -> log

Usage:
  # Basic example with epsilon-greedy agent
  python runner/one_step.py --trace demo/trace-0001.msgpack --ns virtual-default --deploy web --target 3 --duration 60

  # With shaped reward for better RL training
  python runner/one_step.py --trace demo/trace-scaling-v2.msgpack --ns virtual-default --deploy web --target 3 --duration 60 --reward shaped
"""
import argparse
import json
import logging
import sys
import time
import hashlib
import random
import shutil
from pathlib import Path
from datetime import datetime, timezone

# Add project root to Python path (must be before local imports)
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.agent import Agent, AgentType

# Import project modules
from ops.hooks import run_hooks
from env import create_simulation, wait_fixed, delete_simulation
from observe.reader import observe, current_requests
from observe.reward import get_reward
from env.actions.trace_io import load_trace, save_trace
from env.actions.ops import bump_cpu_small, bump_mem_small, scale_up_replicas
from runner.safeguards import validate_action
from runner.policies import get_policy

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

# ---- Helper function to extract current resource state from trace ----
def _extract_current_state(trace: list, deploy: str) -> dict:
    """
    Extract current CPU, memory, and replicas for a deployment from the trace.
    Returns dict with 'cpu', 'memory', 'replicas' keys.
    """
    current_state = {
        "cpu": "0m",
        "memory": "0Mi",
        "replicas": 0
    }
    
    # Search through trace events for the target deployment
    events = trace.get("events", [])
    for event in events:
        applied_objs = event.get("applied_objs", [])
        for obj in applied_objs:
            if obj.get("kind") == "Deployment" and obj.get("metadata", {}).get("name") == deploy:
                spec = obj.get("spec", {})
                template = spec.get("template", {})
                containers = template.get("spec", {}).get("containers", [])
                
                # Get replicas
                current_state["replicas"] = spec.get("replicas", 0)
                
                # Get CPU and memory from first container (typical pattern)
                if containers:
                    resources = containers[0].get("resources", {})
                    requests = resources.get("requests", {})
                    current_state["cpu"] = requests.get("cpu", "0m")
                    current_state["memory"] = requests.get("memory", "0Mi")
                
                return current_state  # Found it, return early
    
    return current_state

# ---- Action application (simplified from action_applier.py) ----
def apply_action(trace_path: str, action: dict, deploy: str, output_path: str) -> tuple[str, dict]:
    """Apply an action to a trace file with safeguard validation. Returns (output_path, info_dict)."""
    # Load trace to get current state for validation
    trace = load_trace(trace_path)
    
    # Extract current resource values from the trace for the target deployment
    current_state = _extract_current_state(trace, deploy)
    
    # Validate action with current state
    is_valid, error_msg = validate_action(action, current_state=current_state)
    if not is_valid:
        logger.warning(f"⚠️  Action blocked by safeguards: {error_msg}")
        # Return unchanged trace
        save_trace(trace, output_path)
        return output_path, {
            "changed": False,
            "action_type": action.get("type"),
            "blocked": True,
            "error": error_msg
        }
    
    action_type = action.get("type", "noop")
    changed = False
    
    if action_type == "noop":
        # No change, just save trace as-is
        save_trace(trace, output_path)
    elif action_type == "bump_cpu_small":
        changed = bump_cpu_small(trace, deploy, step=action.get("step", "500m"))
        save_trace(trace, output_path)
    elif action_type == "bump_mem_small":
        changed = bump_mem_small(trace, deploy, step=action.get("step", "256Mi"))
        save_trace(trace, output_path)
    elif action_type == "scale_up_replicas":
        changed = scale_up_replicas(trace, deploy, delta=action.get("delta", 1))
        save_trace(trace, output_path)
    else:
        raise ValueError(f"Unknown action type: {action_type}")
    
    info = {"changed": changed, "action_type": action_type, "blocked": False}
    return output_path, info

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
 
# ---- Main orchestration ----
def one_step(trace_path: str, namespace: str, deploy: str, target: int, duration: int, seed: int = 0, agent_name: str = "heuristic", reward_name: str = "base", agent = None):
    random.seed(seed)
    
    timestamp = datetime.now(timezone.utc).isoformat() 
    local_trace_path = str(trace_path)
    tmp_dir = Path(".tmp")
    tmp_dir.mkdir(parents=True, exist_ok=True)
    out_trace_path = str(tmp_dir / "trace-next.msgpack")

    # SimKube driver reads trace at file:///data/<filename> (mounted from kind node data dir)
    trace_filename = Path(local_trace_path).name
    cluster_trace_path = f"file:///data/{trace_filename}"
    
    sim_name = f"diag-{deterministic_id(local_trace_path, namespace, deploy, target, timestamp)}"
    
    # NOTE: SimKube creates pods in virtual-<trace-namespace>
    # The trace file specifies namespace "default", so pods appear in "virtual-default"
    virtual_namespace = "virtual-default"
    
    logger.info(f"Starting one_step run: sim_name={sim_name}, ns={namespace} (virtual={virtual_namespace}), trace={cluster_trace_path}, deploy={deploy}, target={target}, duration={duration}, agent={agent_name}")

    sim_uid = None
    start_time = time.time()
    record = None
    trace_changed = False

    try:
        # 1) pre_start hook
        # NOTE: Clean up virtual namespace where SimKube creates pods
        logger.info(f"Running pre_start hooks in {virtual_namespace}...")
        run_hooks("pre_start", virtual_namespace)
        logger.info("pre_start hooks completed.")
        
        # 2) create simulation CR (use cluster path)
        logger.info("Creating simulation CR...")
        sim_uid = create_simulation(name=sim_name, trace_path=cluster_trace_path, duration_s=duration, namespace=namespace)
        logger.info(f"Created simulation (uid={sim_uid}).")
        
        # 3) wait fixed (block until observation time)
        logger.info(f"Waiting fixed duration: {duration}s ...")
        wait_fixed(duration)
        logger.info("Wait complete, proceeding to observe.")
        
        # 4) observe cluster state
        logger.info(f"Observing cluster state in {virtual_namespace}...")
        obs = observe(virtual_namespace, deploy)
        logger.info(f"Observation: {obs}")
        resources = current_requests(virtual_namespace, deploy)
        logger.info(f"Current requests: {resources}")

        
        # 5) Policy/agent decision
        ACTION_SPACE = {
            0: {"type": "noop"},
            1: {"type": "bump_cpu_small", "step": "500m"},
            2: {"type": "bump_mem_small", "step": "256Mi"},
            3: {"type": "scale_up_replicas", "delta": 1},
        }

        if agent_name == "greedy" and agent is not None:
            action_idx = agent.act()
            action = ACTION_SPACE.get(action_idx, {"type": "noop"})
            logger.info(f"Agent '{agent_name}' chose action index: {action_idx}")
        elif agent_name == "dqn" and agent is not None:
            dqn_state = [
                int(resources["cpu"].rstrip("m") or 0),
                int(str(resources["memory"]).rstrip("Mi") or 0),
                resources["replicas"],
                obs.get("pending", 0),
            ]
            action_idx = agent.act(dqn_state)
            action = ACTION_SPACE.get(action_idx, {"type": "noop"})
            logger.info(f"Agent '{agent_name}' chose action index: {action_idx}")
        else:
            # Policy-based (heuristic, scale_replicas, etc.)
            policy_fn = get_policy(agent_name)
            action = policy_fn(obs=obs, deploy=deploy)
            logger.info(f"Policy '{agent_name}' chose action: {action}")
        
        # 6) Apply action to trace (use local path)
        logger.info(f"Applying action: {action}")
        out_trace_path, action_info = apply_action(local_trace_path, action, deploy, out_trace_path)
        trace_changed = action_info.get("changed", False)
        logger.info(f"Action complete. Changed: {trace_changed}")
        
        # 6b) Copy output trace to kind node data directory (always, for multi-step runs)
        kind_data_dir = Path.home() / ".local/kind-node-data/cluster"
        kind_data_dir.mkdir(parents=True, exist_ok=True)
        trace_filename = Path(out_trace_path).name
        kind_trace_path = kind_data_dir / trace_filename
        if Path(out_trace_path).exists():
            shutil.copy2(out_trace_path, kind_trace_path)
            logger.info(f"Copied trace to kind: {kind_trace_path}")
        
        # 7) Compute reward
        reward_fn = get_reward(reward_name)
        r = reward_fn(obs=obs, target_total=target, T_s=duration, resources=resources)

        # Update agent (only for learning agents)
        if agent_name == "greedy" and agent is not None:
            agent.update(action_idx, r)
        elif agent_name == "dqn" and agent is not None:
            obs_new = observe(virtual_namespace, deploy)
            resources_new = current_requests(virtual_namespace, deploy)
            dqn_state_new = [
                int(str(resources_new["cpu"]).rstrip("m") or 0),
                int(str(resources_new["memory"]).rstrip("Mi") or 0),
                resources_new["replicas"],
                obs_new.get("pending", 0),
            ]
            agent.update(dqn_state, action_idx, dqn_state_new, r, True)

        logger.info(f"Reward computed: {r}")
        
        # 8) write logs: step.jsonl and summary.json
        record = {
            "timestamp": timestamp,
            "sim_name": sim_name,
            "sim_uid": sim_uid,
            "namespace": virtual_namespace,  # Use actual namespace where resources exist
            "trace_in": local_trace_path,
            "trace_out": out_trace_path,
            "obs": obs,
            "action": action,
            "action_info": action_info if action_info else {},
            "reward": float(r),  # Keep as float for shaped rewards
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
    # Return structured result for programmatic use
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
    parser.add_argument("--reward", type=str, default="base", help="Reward function to use (base, shaped, max_punish)")


    args = parser.parse_args()

    agent = None
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
    elif args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=4, n_actions=4)
    # else: use policy (heuristic, scale_replicas, etc.) via get_policy

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
    
