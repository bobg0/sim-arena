"""
runner/train.py

Overarching training loop that runs multiple episodes of the simulation,
manages agent persistence, and automatically saves checkpoints.

Sample usage:
  # Train on 6 trace types (random per episode), logs to terminal
  PYTHONPATH=. python runner/train.py --trace demo --ns test-ns --deploy web --target 3 \\
    --agent dqn --episodes 50 --steps 10 --duration 60

  # Redirect logs to checkpoint folder (for background/long runs)
  PYTHONPATH=. python runner/train.py --trace demo --ns test-ns --target 3 --agent dqn \\
    --episodes 50 --log-to-checkpoint

  # Single trace (legacy)
  PYTHONPATH=. nohup python runner/train.py --trace demo/trace-0001.msgpack --ns test-ns --target 3 --agent dqn &

  # Resume from checkpoint (reuses checkpoint folder, resumes from last episode)
  PYTHONPATH=. python runner/train.py --trace demo --ns test-ns --target 3 --agent dqn \\
    --load checkpoints/dqn_20260221_20/checkpoint_latest.pt --episodes 50

Important Notes:
Before running, ensure you run the following commands to clean up any ghost simulations:
    pkill -f "train.py.*--ns <your-namespace>"
    kubectl delete simulations.simkube.io --all -n <your-namespace>
"""

import sys
import os
import json
import re
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
    parser.add_argument("--trace", required=True, help="Trace path: single .msgpack file, or directory of traces (randomly sampled per episode)")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    parser.add_argument("--target", type=int, required=True, help="Target total pods")
    
    # Optional arguments with defaults
    parser.add_argument("--deploy", type=str, default="web", help="Deployment name (default: web)")
    parser.add_argument("--duration", type=int, default=90, help="Duration per step in seconds (default: 90)")
    parser.add_argument("--steps", type=int, default=200, help="Max steps per episode (default: 200)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (random if not specified)")
    parser.add_argument("--agent", type=str, default="greedy", help="Agent to use (default: greedy)")
    parser.add_argument("--Naction", type=int, default=4, help="number of actions for the agent (default: 4, don't use reduction actions)")
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (default: shaped)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    # Training & Checkpointing arguments
    parser.add_argument("--episodes", type=int, default=200, help="Number of episodes to train (default: 200)")
    parser.add_argument("--checkpoint-interval", type=int, default=10, help="Save checkpoint every N episodes")
    parser.add_argument("--load", type=str, default=None, help="Path to load an initial agent checkpoint")
    parser.add_argument("--resume-folder", action="store_true", help="If --load is used, save new checkpoints in the loaded model's folder instead of creating a new one")
    parser.add_argument("--start-episode", type=int, default=None, help="Override start episode when resuming (default: auto-detect from checkpoint_epN)")
    parser.add_argument("--save", type=str, default=None, help="Optional explicit path to save the final agent")
    parser.add_argument("--log-to-terminal", action="store_true", help="Print all logs to terminal (default: redirect logs to checkpoint folder)")

    # DQN Hyperparameters (Optional)
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate for DQN (default: 0.001)")
    parser.add_argument("--gamma", type=float, default=0.97, help="Discount factor (default: 0.97)")
    parser.add_argument("--eps-start", type=float, default=1.0, help="Starting epsilon (default: 1.0)")
    parser.add_argument("--eps-end", type=float, default=0.1, help="Ending epsilon (default: 0.1)")
    parser.add_argument("--eps-decay", type=int, default=1000, help="Epsilon decay steps (default: 1000)")
    parser.add_argument("--buffer-size", type=int, default=2000, help="Replay buffer size (default: 2000)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size (default: 32)")
    parser.add_argument("--target-update", type=int, default=50, help="Target network update frequency (default: 50)")

    # cost_aware_v2 reward tuning
    parser.add_argument("--step-penalty", type=float, default=0.0, help="Per-step penalty to favor faster fixes (default: 0)")
    parser.add_argument("--obs-noise", type=float, default=0.0, help="Obs noise std for sim-to-real robustness (default: 0)")

    args = parser.parse_args()

    # Traces with incompatible SimKube v2 format (cause 404 "web" deployment not found)
    TRACE_EXCLUDE = {"trace-v2.msgpack"}

    # Resolve trace path(s): dir -> list of .msgpack, file -> single-item list
    trace_path_arg = Path(args.trace)
    if trace_path_arg.is_dir():
        trace_paths = sorted(trace_path_arg.glob("*.msgpack"))
        trace_paths = [p for p in trace_paths if p.name not in TRACE_EXCLUDE]
        if not trace_paths:
            raise SystemExit(f"No .msgpack traces found in {trace_path_arg}")
        trace_paths = [str(p) for p in trace_paths]
    else:
        trace_paths = [args.trace]

    # Resolve reproducibility
    base_seed = args.seed if args.seed is not None else random.randint(0, 999999)
    # Ensure the randomly generated seed is saved in the args namespace for logging
    args.seed = base_seed

    # Setup checkpoint directory: reuse folder when resuming ONLY IF --resume-folder is passed
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S") # Added %M%S to prevent collisions on rapid restarts
    
    if args.load:
        load_path = Path(args.load).resolve()
        if not load_path.exists():
            raise SystemExit(f"--load path not found: {args.load}")
            
        if args.resume_folder:
            checkpoint_folder = load_path.parent
            logger.info(f"Resuming in existing folder: {checkpoint_folder}")
        else:
            checkpoint_folder = project_root / "checkpoints" / f"{args.agent}_{timestamp}"
            logger.info(f"Loading weights from {load_path}, but saving to NEW folder: {checkpoint_folder}")
    else:
        checkpoint_folder = project_root / "checkpoints" / f"{args.agent}_{timestamp}"
        
    checkpoint_folder.mkdir(parents=True, exist_ok=True)

    log_file = None
    if not args.log_to_terminal:
        log_file_path = checkpoint_folder / "train.log"
        log_file = open(log_file_path, "a", buffering=1)
        print(f"Logs → {log_file_path}", flush=True)
        sys.stdout.flush()
        sys.stderr.flush()
        os.dup2(log_file.fileno(), sys.stdout.fileno())
        os.dup2(log_file.fileno(), sys.stderr.fileno())

    # Configure root logger to output to the redirected sys.stdout
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    logger.info(f"Using base random seed: {base_seed}")
    logger.info(f"Checkpoints: {checkpoint_folder}")
    logger.info(f"Trace pool: {len(trace_paths)} trace(s) — random per episode")

    # Save the exact command and all parsed args
    command_log_path = checkpoint_folder / "command.txt"
    with open(command_log_path, "w") as f:
        f.write("=== Command Run ===\n")
        f.write(" ".join(sys.argv) + "\n\n")
        f.write("=== Parsed Arguments ===\n")
        for key, value in vars(args).items():
            f.write(f"{key}: {value}\n")
        f.write(f"\nTrace pool ({len(trace_paths)}):\n")
        for p in trace_paths:
            f.write(f"  - {p}\n")

    # Initialize the agent
    agent = None
    file_ext = ".json"
    # Must match ACTION_SPACE in one_step.py (7 actions: noop, bump_cpu, bump_mem, scale_up, reduce_cpu, reduce_mem, scale_down)
    # state_dim must match dqn_state in one_step.py: [cpu_m/4000, mem_mi/4096, pending/5, distance/5, replicas/8] = 5
    n_actions = 7
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=args.Naction, epsilon=0.1)
        file_ext = ".json"
    elif args.agent == "dqn":
        agent = Agent(
            AgentType.DQN,
            state_dim=4,  # [current_pods, cpu_util, mem_util, target_pods]
            n_actions=args.Naction,
            learning_rate=args.lr,
            gamma=args.gamma,
            eps_start=args.eps_start,
            eps_end=args.eps_end,
            eps_decay_steps=args.eps_decay,
            replay_buffer_size=args.buffer_size,
            batch_size=args.batch_size,
            target_update_freq=args.target_update
        )
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

   # When resuming, start from the episode after the last completed one
    start_ep = 1
    if args.start_episode is not None:
        start_ep = max(1, args.start_episode)
        if args.load:
            logger.info(f"Starting from episode {start_ep} (--start-episode override)")
    elif args.load:
        last_ep = 0
        if str(args.load).endswith(".pt"):
            try:
                import torch
                # Load the checkpoint dict directly to read the episode history length
                checkpoint_data = torch.load(args.load, map_location="cpu", weights_only=False)
                last_ep = len(checkpoint_data.get('episode_reward_history', []))
            except Exception as e:
                logger.warning(f"Failed to extract episode history from checkpoint: {e}")
        else:
            # Basic fallback for non-PyTorch agents (like greedy JSON saves)
            try:
                with open(args.load, "r") as f:
                    data = json.load(f)
                    last_ep = len(data.get('episode_reward_history', []))
            except Exception:
                pass
                
        if last_ep > 0:
            start_ep = last_ep + 1
            logger.info(f"Resuming from episode {start_ep} (read {last_ep} completed episodes directly from checkpoint)")
        else:
            logger.info("Resuming from episode 1 (could not find episode history in checkpoint)")

    if start_ep > args.episodes:
        logger.info(f"Training already complete (reached episode {start_ep - 1}). Nothing to do.")
        return 0

    # Training Loop
    start_time = time.time()
    
    try:
        for ep in range(start_ep, args.episodes + 1):
            ep_seed = base_seed + ep * 1000
            trace_path = random.choice(trace_paths) if len(trace_paths) > 1 else trace_paths[0]
            
            logger.info("=" * 60)
            logger.info(f"🚀 Episode {ep}/{args.episodes} | trace: {Path(trace_path).name}")
            logger.info("=" * 60)
            
            # Build reward_kwargs for cost_aware_v2
            reward_kwargs = None
            if args.reward == "cost_aware_v2":
                reward_kwargs = {"step_penalty": args.step_penalty}

            # Run the episode
            result = run_episode(
                trace_path=trace_path,
                namespace=args.namespace,
                deploy=args.deploy,
                target=args.target,
                duration=args.duration,
                steps=args.steps,
                seed=ep_seed,
                agent_name=args.agent,
                reward_name=args.reward,
                agent=agent,
                reward_kwargs=reward_kwargs,
                obs_noise_scale=args.obs_noise,
            )
            
            if result["status"] != 0:
                logger.error(f"Episode {ep} failed. Stopping training.")
                break
                
            if agent is not None:
                # Always save the 'latest' state
                agent.save(str(latest_ckpt_path))
                with open(progress_path, "w") as f:
                    json.dump({"episode": ep}, f)
                try:
                    agent.visualize(save_path=str(latest_plot_path))
                    agent.plot_learning_curve(save_path=str(latest_curve_path))
                except Exception as e:
                    logger.warning(f"Skipping visualization (install matplotlib for plots): {e}")
                
                # Periodically save historical checkpoints and visualizations
                if ep % args.checkpoint_interval == 0:
                    ckpt_path = checkpoint_folder / f"checkpoint_ep{ep}{file_ext}"
                    plot_path = checkpoint_folder / f"agent_visualization_ep{ep}.png"
                    
                    agent.save(str(ckpt_path))
                    agent.visualize(save_path=str(plot_path))
                    
                    logger.info(f"💾 Saved interval checkpoint and visualizations for Episode {ep}")

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Training interrupted by user (KeyboardInterrupt).")
        logger.info("Saving current state before exiting...")
    finally:
        # Final Checkpoints & Saves (Runs whether training completes, fails, or is interrupted)
        if agent is not None:
            # Ensure the latest is up to date in case of interruption
            agent.save(str(latest_ckpt_path))
            try:
                agent.visualize(save_path=str(latest_plot_path))
                agent.plot_learning_curve(save_path=str(latest_curve_path))
            except Exception as e:
                logger.warning(f"Skipping visualization: {e}")
                
            logger.info(f"💾 Ensured latest training checkpoint: {latest_ckpt_path}")
            
            if args.save:
                agent.save(args.save)
                logger.info(f"💾 Saved explicit copy of final agent to: {args.save}")

        total_time = time.time() - start_time
        logger.info(f"🏁 Training process ended! Total time: {total_time / 60:.2f} minutes.")
        
        if log_file is not None:
            log_file.close()
        
    return 0

if __name__ == "__main__":
    sys.exit(main())