"""
runner/multi_step.py

Run multiple sequential agent steps (episodes) using the existing one_step runner.
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
    agent=None,
    reward_kwargs=None,
    obs_noise_scale: float = 0.0,
    min_return: float = None,
    state_space: str = "base",
    updates_per_step: int = 4,  # Default to 4 updates per step
):
    """
    Run a multi-step episode.
    Returns: dict with episode summary
    """
    logger.info(f"Starting episode: max_steps={steps}, trace={trace_path}, agent={agent_name}, updates_per_step={updates_per_step}")

    current_trace = trace_path
    episode_records = []
    total_reward = 0
    start_time = time.time()

    prev_dqn_state = None
    prev_action_idx = None
    done = False

    for step_idx in range(steps+1):
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
            agent=agent,
            step_idx=step_idx,
            reward_kwargs=reward_kwargs,
            obs_noise_scale=obs_noise_scale,
            state_space=state_space,
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
                # Add transition to buffer and trigger the FIRST train step
                agent.update(
                    state=prev_dqn_state, 
                    action=prev_action_idx, 
                    next_state=curr_dqn_state, 
                    reward=curr_reward, 
                    done=done
                )
                
                for _ in range(updates_per_step - 1):
                        underlying_agent._train_step()

        if done:
            logger.info(f"🎯 Target state reached at State {step_idx}! Terminating episode early.")
            break
        
        if min_return is not None and total_reward < min_return:
            logger.info(f"📉 Total return ({total_reward}) dropped below minimum threshold ({min_return}). Terminating episode early.")
            break
        
        if step_idx == steps:
            logger.info(f"⏳ Max steps ({steps}) reached. Terminating episode early.")
            break

        prev_dqn_state = curr_dqn_state
        prev_action_idx = curr_action_idx
    
    if agent_name == "dqn" and agent is not None and not done:
        agent.episode_reward_history.append(agent.current_episode_reward)
        agent.current_episode_reward = 0.0

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
    parser.add_argument("--state-space", type=str, default="base", help="State space representation")
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (base, shaped, max_punish)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"], help="Set the logging level")
    parser.add_argument("--load", type=str, default=None, help="Path to load an existing agent checkpoint")
    parser.add_argument("--save", type=str, default=None, help="Path to save the agent checkpoint after the episode")
    parser.add_argument("--updates-per-step", type=int, default=4, help="Number of gradient updates per environment step")

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
        agent = Agent(AgentType.DQN, state_dim=5, n_actions=7)

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
        state_space=args.state_space,
        updates_per_step=args.updates_per_step,
    )

    if agent is not None and args.save:
        logger.info(f"Saving updated agent weights to {args.save}...")
        agent.save(args.save)

    return 0 if result["status"] == 0 else 1

if __name__ == "__main__":
    sys.exit(main())