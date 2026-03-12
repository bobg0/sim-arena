"""
runner/train_gym.py

A standard reinforcement learning training loop using the Gymnasium API.
This script trains an agent (e.g., DQN) to scale a Kubernetes deployment
to a target replica count over multiple episodes.

Usage:
  python runner/train_gym.py \
    --trace demo/trace-0001.msgpack \
    --ns test-ns \
    --deploy web \
    --target 3 \
    --episodes 10 \
    --steps 5 \
    --agent dqn \
    --save models/dqn_gym_model.pt
"""

import sys
import argparse
import logging
import time
from pathlib import Path
import numpy as np
import gymnasium as gym

# Ensure project root is in the Python path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Importing env registers 'SimKube-v0' via env/__init__.py
import env 
from agent.agent import Agent, AgentType

logger = logging.getLogger("train_gym")

def train(args):
    """Main training loop."""
    
    # 1. Initialize the Environment
    logger.info(f"Initializing SimKube-v0 environment...")
    gym_env = gym.make(
        "SimKube-v0",
        initial_trace_path=args.trace,
        namespace=args.namespace,
        deploy=args.deploy,
        target=args.target,
        duration=args.duration,
        reward_name=args.reward,
        max_steps=args.steps
    )
    
    # 2. Initialize the Agent
    state_dim = gym_env.observation_space.shape[0]
    n_actions = gym_env.action_space.n
    
    agent = None
    if args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=state_dim, n_actions=n_actions)
    elif args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=n_actions, epsilon=0.1)
    else:
        raise ValueError(f"Unsupported agent type: {args.agent}")

    if args.load:
        logger.info(f"Loading agent weights from {args.load}...")
        agent.load(args.load)

    # 3. Training Loop
    logger.info(f"Starting training for {args.episodes} episodes...")
    best_reward = -np.inf

    for episode in range(1, args.episodes + 1):
        # Reset the environment at the start of each episode
        state, info = gym_env.reset(seed=args.seed + episode)
        done = False
        total_reward = 0
        step = 0
        
        start_time = time.time()

        while not done:
            step += 1
            
            # Agent selects an action based on the 5D state array
            if args.agent == "dqn":
                action = agent.act(state)
            else:
                action = agent.act() # Greedy acts without state

            # Step the environment forward
            next_state, reward, terminated, truncated, step_info = gym_env.step(action)
            
            done = terminated or truncated
            total_reward += reward
            
            # Update the agent's neural network/Q-table
            if args.agent == "dqn":
                agent.update(
                    state=state, 
                    action=action, 
                    next_state=next_state, 
                    reward=reward, 
                    done=terminated  # Only pass True if it naturally finished (hit target)
                )
            elif args.agent == "greedy":
                agent.update(action, reward)
            
            # Move to the next state
            state = next_state

        # Episode cleanup and logging
        if args.agent == "dqn":
            agent.episode_reward_history.append(agent.current_episode_reward)
            agent.current_episode_reward = 0.0

        elapsed = time.time() - start_time
        logger.info(f"Episode {episode:03d}/{args.episodes} | "
                    f"Steps: {step} | "
                    f"Reward: {total_reward:.2f} | "
                    f"Target Reached: {terminated} | "
                    f"Time: {elapsed:.1f}s")
        
        # Save best model
        if args.save and total_reward > best_reward:
            best_reward = total_reward
            save_path = Path(args.save)
            save_path.parent.mkdir(parents=True, exist_ok=True)
            logger.info(f"New best reward! Saving agent to {save_path}...")
            agent.save(str(save_path))

    gym_env.close()
    logger.info("Training complete!")

def main():
    parser = argparse.ArgumentParser(description="Train RL agent using Gymnasium API")
    parser.add_argument("--trace", required=True, help="Initial trace path")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True)
    parser.add_argument("--deploy", required=True)
    parser.add_argument("--target", type=int, required=True)
    parser.add_argument("--duration", type=int, default=60, help="Simulation duration (seconds)")
    parser.add_argument("--episodes", type=int, default=10, help="Number of training episodes")
    parser.add_argument("--steps", type=int, default=5, help="Max steps per episode")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--agent", type=str, default="dqn", choices=["dqn", "greedy"])
    parser.add_argument("--reward", type=str, default="shaped")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING"])
    parser.add_argument("--load", type=str, default=None, help="Path to load model weights")
    parser.add_argument("--save", type=str, default=None, help="Path to save best model weights")

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    train(args)

if __name__ == "__main__":
    sys.exit(main())