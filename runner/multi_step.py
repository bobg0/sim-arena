"""
runner/multi_step.py

Run multiple sequential agent steps (episodes) using the existing one_step runner.

Sample usage:

# Use scale_replicas to grow pods each step (good for testing multi-step)
PYTHONPATH=. python runner/multi_step.py \
  --trace demo/trace-scaling-v2.msgpack \
  --ns test-ns \
  --deploy web \
  --target 5 \
  --steps 5 \
  --agent greedy \
  --log-level DEBUG

# Use dqn agent to learn over multiple steps (good for testing learning)
python runner/multi_step.py  --trace demo/trace-0001.msgpack  --deploy web \
--agent dqn  --ns test-ns  --target 3  --steps 5 


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

def run_episode(
    trace_path: str,
    namespace: str,
    deploy: str,
    target: int,
    duration: int,
    steps: int,
    seed: int = 0,
    agent_name: str = "greedy",
    reward_name: str = "shaped",
    agent = None
):
    """
    Run a multi-step episode.
    Returns: dict with episode summary
    """
    logger.info(f"Starting episode: max_steps={steps}, trace={trace_path}, agent={agent_name}")

    current_trace = trace_path
    episode_records = []
    total_reward = 0
    start_time = time.time()

    prev_dqn_state = None
    prev_action_idx = None

    for step_idx in range(steps):
        # Kept at debug so it doesn't flood standard training logs
        logger.debug(f"--- Processing State {step_idx} ---")
        logger.debug(f"Using trace: {current_trace}")

        result = one_step(
            trace_path=current_trace,
            namespace=namespace,
            deploy=deploy,
            target=target,
            duration=duration,
            seed=seed + step_idx,
            agent_name=agent_name,
            reward_name=reward_name,
            agent=agent
        )

        if result["status"] != 0:
            logger.error(f"State {step_idx} failed, aborting episode.")
            break

        record = result["record"]
        episode_records.append(record)

        current_trace = record["trace_out"]
        total_reward += record.get("reward", 0)

        curr_dqn_state = record.get("dqn_state")
        curr_action_idx = record.get("action_idx")
        curr_reward = record.get("reward", 0)

        obs = record.get("obs", {})
        ready = obs.get("ready", 0)
        total = obs.get("total", 0)
        pending = obs.get("pending", 0)
        
        done = (ready == target and total == target and pending == 0)

        # Agent Update logic
        if step_idx > 0 and agent is not None:
            if agent_name == "greedy" and prev_action_idx is not None:
                agent.update(prev_action_idx, curr_reward)
            elif agent_name == "dqn" and prev_dqn_state is not None:
                agent.update(
                    state=prev_dqn_state, 
                    action=prev_action_idx, 
                    next_state=curr_dqn_state, 
                    reward=curr_reward, 
                    done=done
                )

        if done:
            logger.info(f"🎯 Target state reached at State {step_idx}! Terminating episode early.")
            break

        prev_dqn_state = curr_dqn_state
        prev_action_idx = curr_action_idx

    elapsed = time.time() - start_time

    logger.info("=" * 60)
    logger.info("Episode completed")
    logger.info(f"States evaluated: {len(episode_records)}")
    logger.info(f"Total reward: {total_reward}")
    logger.info(f"Elapsed time: {elapsed:.2f}s")
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
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (base, shaped, max_punish)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set the logging level")
    parser.add_argument("--load", type=str, default=None, help="Path to load an existing agent checkpoint")
    parser.add_argument("--save", type=str, default=None, help="Path to save the agent checkpoint after the episode")

    args = parser.parse_args()

    # Configure root logger based on parsed arguments
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    agent = None
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=7, epsilon=0.1)
    elif args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=4, n_actions=7)

    if agent is not None and args.load:
        logger.info(f"Loading agent weights from {args.load}...")
        agent.load(args.load)

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

    if agent is not None and args.save:
        logger.info(f"Saving updated agent weights to {args.save}...")
        agent.save(args.save)

    return 0 if result["status"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())