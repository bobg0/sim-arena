"""
runner/multi_step.py

Run multiple sequential agent steps (episodes) using the existing one_step runner.

Sample usage:

python runner/multi_step.py \
  --trace demo/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --steps 5
"""

import sys
from pathlib import Path
import argparse
import logging
import time

from agent.agent import Agent, AgentType

# Add project root to Python path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from runner.one_step import one_step

logger = logging.getLogger("multi_step")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def run_episode(
    trace_path: str,
    namespace: str,
    deploy: str,
    target: int,
    duration: int,
    steps: int,
    seed: int = 0,
    agent_name: str = "greedy",
    reward_name: str = "base",
    agent = None
):
    """
    Run a multi-step episode.

    Returns:
        dict with episode summary
    """
    logger.info(
        f"Starting episode: steps={steps}, trace={trace_path}, agent={agent_name}"
    )

    current_trace = trace_path
    episode_records = []
    total_reward = 0
    start_time = time.time()

    for step_idx in range(steps):
        logger.info("-" * 60)
        logger.info(f"Episode step {step_idx + 1}/{steps}")
        logger.info(f"Using trace: {current_trace}")

        result = one_step(
            trace_path=current_trace,
            namespace=namespace,
            deploy=deploy,
            target=target,
            duration=duration,
            seed=seed + step_idx,  # deterministic but varied
            agent_name=agent_name,
            reward_name=reward_name,  # Pass the reward function name
            agent=agent
        )

        if result["status"] != 0:
            logger.error(f"Step {step_idx} failed, aborting episode.")
            break

        record = result["record"]
        episode_records.append(record)

        # Update trace for next step
        current_trace = record["trace_out"]

        # Accumulate reward
        total_reward += record.get("reward", 0)

        # ---------------------------------------------------------
        # AUTO-TERMINATION LOGIC
        # ---------------------------------------------------------
        obs = record.get("obs", {})
        ready = obs.get("ready", 0)
        total = obs.get("total", 0)
        pending = obs.get("pending", 0)
        
        # Check if we have achieved the perfect target state
        if ready == target and total == target and pending == 0:
            logger.info(f"🎯 Target state reached at step {step_idx + 1}! Terminating episode early.")
            break

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.info("Episode completed")
    logger.info(f"Steps executed: {len(episode_records)}")
    logger.info(f"Total reward: {total_reward}")
    logger.info(f"Elapsed time: {elapsed:.2f}s")
    logger.info(f"Final trace: {current_trace}")
    logger.info("=" * 60)

    return {
        "status": 0,
        "steps_executed": len(episode_records),
        "total_reward": total_reward,
        "elapsed_s": elapsed,
        "final_trace": current_trace,
        "records": episode_records,
    }


def main():
    parser = argparse.ArgumentParser(description="Run multiple RL steps")
    parser.add_argument("--trace", required=True, help="Initial trace path")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True)
    parser.add_argument("--deploy", required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--duration", type=int, default=60)
    parser.add_argument("--steps", type=int, default=5, help="Number of steps per episode")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--agent", type=str, default="greedy", help="Agent to use")
    parser.add_argument("--reward", type=str, default="base", help="Reward function to use (base, shaped, max_punish)")

    args = parser.parse_args()

    # Only create agent for learning agents; policy-based agents use get_policy()
    agent = None
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
    elif args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=4, n_actions=4)
    # else: heuristic, scale_replicas, etc. use policy via one_step

    result = run_episode(
        trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        steps=args.steps,
        seed=args.seed,
        agent_name=args.agent,
        reward_name=args.reward,
        agent=agent,
    )
    return 0 if result["status"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
