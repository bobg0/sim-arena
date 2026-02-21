"""
runner/train.py

Overarching training loop that runs multiple episodes of the simulation,
manages agent persistence, and automatically saves checkpoints.

Sample usage:
  # Train a DQN agent for 50 episodes in the background.
  # (stdout and stderr will automatically save to train.log inside the new checkpoint folder)
  nohup python runner/train.py \
    --trace demo/trace-0001.msgpack \
    --ns virtual-default \
    --deploy web \
    --target 3 \
    --agent dqn \
    --episodes 50 &

  # Resume training from a specific checkpoint in the background
  nohup python runner/train.py \
    --trace demo/trace-0001.msgpack \
    --ns virtual-default \
    --target 3 \
    --agent dqn \
    --load checkpoints/dqn_20260218_22/checkpoint_ep20.pt \
    --episodes 50 &
"""

import sys
import os
import argparse
import logging
import time
import random
from pathlib import Path
from datetime import datetime

# Add project root to Python path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from agent.agent import Agent, AgentType
from runner.multi_step import run_episode

logger = logging.getLogger("train")

def main():
    parser = argparse.ArgumentParser(description="Run continuous RL training over multiple episodes.")
    
    # Required arguments
    parser.add_argument("--trace", required=True, help="Initial trace path (reused at the start of each episode)")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    parser.add_argument("--target", type=int, required=True, help="Target total pods")
    
    # Optional arguments with defaults
    parser.add_argument("--deploy", type=str, default="web", help="Deployment name (default: web)")
    parser.add_argument("--duration", type=int, default=90, help="Duration per step in seconds (default: 90)")
    parser.add_argument("--steps", type=int, default=200, help="Max steps per episode (default: 200)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (random if not specified)")
    parser.add_argument("--agent", type=str, default="greedy", help="Agent to use (default: greedy)")
    parser.add_argument("--Naction", type=int, default=4, help="number of actions for the agent (default: 4)")
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (default: shaped)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    # Training & Checkpointing arguments
    parser.add_argument("--episodes", type=int, default=200, help="Number of episodes to train (default: 200)")
    parser.add_argument("--checkpoint-interval", type=int, default=10, help="Save checkpoint every N episodes")
    parser.add_argument("--load", type=str, default=None, help="Path to load an initial agent checkpoint")
    parser.add_argument("--save", type=str, default=None, help="Optional explicit path to save the final agent")

    args = parser.parse_args()

    # Resolve reproducibility
    base_seed = args.seed if args.seed is not None else random.randint(0, 999999)
    # Ensure the randomly generated seed is saved in the args namespace for logging
    args.seed = base_seed

    # Setup checkpoint directory
    timestamp = datetime.now().strftime("%Y%m%d_%H")
    checkpoint_folder = project_root / "checkpoints" / f"{args.agent}_{timestamp}"
    checkpoint_folder.mkdir(parents=True, exist_ok=True)


    # Output Redirection & Logging Setup
    log_file_path = checkpoint_folder / "train.log"
    
    # Open the log file and redirect stdout and stderr
    log_file = open(log_file_path, "a", buffering=1)  # line-buffered
    
    # Flush Python buffers before redirecting
    sys.stdout.flush()
    sys.stderr.flush()

    # Force OS file descriptors 1 (stdout) and 2 (stderr) to write to our log file
    os.dup2(log_file.fileno(), sys.stdout.fileno())
    os.dup2(log_file.fileno(), sys.stderr.fileno())

    # Configure root logger to output to the redirected sys.stdout
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    logger.info(f"Using base random seed: {base_seed}")
    logger.info(f"Checkpoints and logs will be saved to: {checkpoint_folder}")

    # Save the exact command and all parsed args
    command_log_path = checkpoint_folder / "command.txt"
    with open(command_log_path, "w") as f:
        f.write("=== Command Run ===\n")
        f.write(" ".join(sys.argv) + "\n\n")
        f.write("=== Parsed Arguments ===\n")
        for key, value in vars(args).items():
            f.write(f"{key}: {value}\n")

    # Initialize the agent
    agent = None
    file_ext = ".json"
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=args.Naction, epsilon=0.1)
        file_ext = ".json"
    elif args.agent == "dqn":
        agent = Agent(AgentType.DQN, state_dim=5, n_actions=args.Naction)
        file_ext = ".pt"
    else:
        logger.warning(f"Using policy-based agent '{args.agent}', checkpointing will be skipped.")

    # Load pre-existing agent if requested
    if agent is not None and args.load:
        logger.info(f"Loading agent weights from {args.load}...")
        agent.load(args.load)

    # File paths for continuous tracking
    latest_ckpt_path = checkpoint_folder / f"checkpoint_latest{file_ext}"
    latest_plot_path = checkpoint_folder / "agent_visualization_latest.png"
    latest_curve_path = checkpoint_folder / "learning_curve_latest.png"

    # Training Loop
    start_time = time.time()
    
    try:
        for ep in range(1, args.episodes + 1):
            logger.info("=" * 60)
            logger.info(f"🚀 Starting Episode {ep}/{args.episodes}")
            logger.info("=" * 60)
            
            # Ensure distinct but reproducible seed for each episode
            ep_seed = base_seed + ep * 1000
            
            # Run the episode
            result = run_episode(
                trace_path=args.trace,
                namespace=args.namespace,
                deploy=args.deploy,
                target=args.target,
                duration=args.duration,
                steps=args.steps,
                seed=ep_seed,
                agent_name=args.agent,
                reward_name=args.reward,
                agent=agent
            )
            
            if result["status"] != 0:
                logger.error(f"Episode {ep} failed. Stopping training.")
                break
                
            if agent is not None:
                agent.save(str(latest_ckpt_path))
                
                agent.visualize(save_path=str(latest_plot_path))
                agent.plot_learning_curve(save_path=str(latest_curve_path))
                
                if ep % args.checkpoint_interval == 0:
                    ckpt_path = checkpoint_folder / f"checkpoint_ep{ep}{file_ext}"
                    agent.save(str(ckpt_path))
                    logger.info(f"💾 Saved interval checkpoint: {ckpt_path}")

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Training interrupted by user (KeyboardInterrupt).")
        logger.info("Saving current state before exiting...")
    finally:
        # Final Checkpoints & Saves (Runs whether training completes, fails, or is interrupted)
        if agent is not None:
            # Ensure the latest is up to date in case of interruption
            agent.save(str(latest_ckpt_path))
            agent.visualize(save_path=str(latest_plot_path))
            agent.plot_learning_curve(save_path=str(latest_curve_path))
                
            logger.info(f"💾 Ensured latest training checkpoint: {latest_ckpt_path}")
            
            if args.save:
                agent.save(args.save)
                logger.info(f"💾 Saved explicit copy of final agent to: {args.save}")

        total_time = time.time() - start_time
        logger.info(f"🏁 Training process ended! Total time: {total_time / 60:.2f} minutes.")
        
        # Close the log file explicitly at the end
        log_file.close()
        
    return 0

if __name__ == "__main__":
    sys.exit(main())