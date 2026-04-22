"""
runner/train.py

Overarching training loop that runs multiple episodes of the simulation,
manages agent persistence, and automatically saves checkpoints.

Sample usage:
  # Train on 6 trace types (random per episode), logs to terminal
  PYTHONPATH=. python runner/train.py --trace demo --ns test-ns --deploy web --target 3 \
    --agent dqn --episodes 50 --steps 10 --duration 60

  # Redirect logs to checkpoint folder (for background/long runs)
  PYTHONPATH=. python runner/train.py --trace demo --ns test-ns --target 3 --agent dqn \
    --episodes 50 --log-to-checkpoint

  # Use Gymnasium API instead of legacy runner
  PYTHONPATH=. python runner/train.py --trace demo/trace-0001.msgpack --ns simkube --target 3 --agent dqn --gym

Important Notes:
Before running, ensure you run the following commands to clean up any ghost simulations:
    pkill -f "train.py.*--ns <your-namespace>"
    kubectl delete simulations.simkube.io --all -n <your-namespace>
"""

import sys
import os
import json
import argparse
import logging
import time
import random
from pathlib import Path
from datetime import datetime

# Add project root to Python path so we can import modules
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# Import Gymnasium
import gymnasium as gym
import env  # This registers 'SimKube-v0' via env/__init__.py

from agent.agent import Agent, AgentType
from runner.multi_step import run_episode

logger = logging.getLogger("train")

def main():
    parser = argparse.ArgumentParser(description="Run continuous RL training over multiple episodes.")
    
    # Required arguments
    parser.add_argument("--trace", required=True, help="Trace path: single .msgpack file, or directory of traces (randomly sampled per episode)")
    parser.add_argument("--ns", "--namespace", dest="namespace", required=True, help="Namespace")
    parser.add_argument("--target", type=int, required=True, help="Target total pods")
    
    # Gymnasium Toggle
    parser.add_argument("--gym", action="store_true", help="Use the Gymnasium API instead of the legacy multi-step runner")

    # Optional arguments with defaults
    parser.add_argument("--deploy", type=str, default="web", help="Deployment name (default: web)")
    parser.add_argument("--duration", type=int, default=40, help="Duration per step in seconds (default: 40)")
    parser.add_argument("--steps", type=int, default=200, help="Max steps per episode (default: 200)")
    parser.add_argument("--seed", type=int, default=None, help="Random seed (random if not specified)")
    parser.add_argument("--agent", type=str, default="greedy", help="Agent to use (default: greedy)")
    parser.add_argument("--Naction", type=int, default=4, help="number of actions for the agent (default: 4)")
    parser.add_argument("--reward", type=str, default="shaped", help="Reward function to use (default: shaped)")
    parser.add_argument("--state-space", type=str, default="base", help="DQN state space representation (default: base)")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    
    # Training & Checkpointing arguments
    parser.add_argument("--episodes", type=int, default=200, help="Number of episodes to train (default: 200)")
    parser.add_argument("--checkpoint-interval", type=int, default=10, help="Save checkpoint every N episodes")
    parser.add_argument("--min-return", type=float, default=None, help="Stop episode early if total return drops below this value")
    parser.add_argument("--load", type=str, default=None, help="Path to load an initial agent checkpoint")
    parser.add_argument("--resume-folder", action="store_true", help="If --load is used, save new checkpoints in the loaded model's folder")
    parser.add_argument("--start-episode", type=int, default=None, help="Override start episode when resuming")
    parser.add_argument("--transfer", action="store_true", help="Transfer learning mode: loads weights but resets history")
    parser.add_argument("--save", type=str, default=None, help="Optional explicit path to save the final agent")
    parser.add_argument("--log-to-terminal", action="store_true", help="Print all logs to terminal")

    # DQN Hyperparameters (Optional)
    parser.add_argument("--lr", type=float, default=0.001, help="Learning rate for DQN (default: 0.001)")
    parser.add_argument("--gamma", type=float, default=0.97, help="Discount factor (default: 0.97)")
    parser.add_argument("--eps-start", type=float, default=1.0, help="Starting epsilon (default: 1.0)")
    parser.add_argument("--eps-end", type=float, default=0.1, help="Ending epsilon (default: 0.1)")
    parser.add_argument("--eps-decay", type=int, default=1000, help="Epsilon decay steps (default: 1000)")
    parser.add_argument("--buffer-size", type=int, default=2000, help="Replay buffer size (default: 2000)")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size (default: 32)")
    parser.add_argument("--target-update", type=int, default=50, help="Target network update frequency (default: 50)")
    parser.add_argument("--updates-per-step", type=int, default=4, help="Number of gradient updates per environment step (default: 4)")

    # cost_aware_v2 reward tuning
    parser.add_argument("--step-penalty", type=float, default=0.0, help="Per-step penalty to favor faster fixes (default: 0)")
    parser.add_argument("--obs-noise", type=float, default=0.0, help="Obs noise std for sim-to-real robustness (default: 0)")

    args = parser.parse_args()

    # Traces with incompatible SimKube v2 format
    TRACE_EXCLUDE = {"trace-v2.msgpack", "trace-scaling-v2.msgpack"}

    # Resolve trace path(s)
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
    args.seed = base_seed

    # Setup checkpoint directory
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
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

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)]
    )

    logger.info(f"Using base random seed: {base_seed}")
    logger.info(f"Checkpoints: {checkpoint_folder}")
    logger.info(f"Gymnasium Mode: {'ENABLED' if args.gym else 'DISABLED'}")

    # Initialize the agent
    agent = None
    file_ext = ".json"
    STATE_DIMS = {"base": 5, "scale": 5}
    state_dim = STATE_DIMS.get(args.state_space, 5)
    
    if args.agent == "greedy":
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=args.Naction, epsilon=0.1)
        file_ext = ".json"
    elif args.agent == "dqn":
        agent = Agent(
            AgentType.DQN,
            state_dim=state_dim,
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
    elif args.agent == "random":
        agent = Agent(AgentType.RANDOM, n_actions=args.Naction)   
        file_ext = ".json"

    # Load pre-existing agent if requested
    if agent is not None and args.load:
        logger.info(f"Loading agent weights from {args.load}...")
        agent.load(args.load)
        if args.transfer:
            agent.reset()

    # File paths for continuous tracking
    latest_ckpt_path = checkpoint_folder / f"checkpoint_latest{file_ext}"
    latest_plot_path = checkpoint_folder / "agent_visualization_latest.png"
    latest_curve_path = checkpoint_folder / "learning_curve_latest.png"

    # Resolve start episode
    start_ep = 1
    if args.start_episode is not None:
        start_ep = max(1, args.start_episode)
    elif args.load:
        last_ep = 0
        if str(args.load).endswith(".pt"):
            try:
                import torch
                checkpoint_data = torch.load(args.load, map_location="cpu", weights_only=False)
                last_ep = len(checkpoint_data.get('episode_reward_history', []))
            except Exception:
                pass
        if last_ep > 0:
            start_ep = 1 if args.transfer else last_ep + 1

    if start_ep > args.episodes:
        logger.info(f"Training already complete. Nothing to do.")
        return 0

    # ==========================
    #      TRAINING LOOP
    # ==========================
    start_time = time.time()
    
    try:
        for ep in range(start_ep, args.episodes + 1):
            ep_seed = base_seed + ep * 1000
            trace_path = random.choice(trace_paths) if len(trace_paths) > 1 else trace_paths[0]
            
            logger.info("=" * 60)
            logger.info(f"🚀 Episode {ep}/{args.episodes} | trace: {Path(trace_path).name}")
            logger.info("=" * 60)

            # ----------------------------------------------------
            # PATH A: GYMNASIUM LOOP
            # ----------------------------------------------------
            if args.gym:
                gym_env = gym.make(
                    "SimKube-v0",
                    initial_trace_path=trace_path,
                    namespace=args.namespace,
                    deploy=args.deploy,
                    target=args.target,
                    duration=args.duration,
                    reward_name=args.reward,
                    max_steps=args.steps
                )
                
                state, info = gym_env.reset(seed=ep_seed)
                done = False
                total_reward = 0
                step = 0
                ep_start_time = time.time()
                
                while not done:
                    step += 1
                    
                    if args.agent == "dqn":
                        action = agent.act(state)
                    else:
                        action = agent.act()

                    next_state, reward, terminated, truncated, step_info = gym_env.step(action)
                    done = terminated or truncated
                    total_reward += reward
                    
                    if args.agent == "dqn":
                        agent.update(
                            state=state, 
                            action=action, 
                            next_state=next_state, 
                            reward=reward, 
                            done=terminated
                        )
                    elif args.agent == "greedy":
                        agent.update(action, reward)
                        
                    state = next_state

                gym_env.close()
                
                # Cleanup agent history for the graph
                if args.agent == "dqn":
                    agent.episode_reward_history.append(agent.current_episode_reward)
                    agent.current_episode_reward = 0.0
                
                ep_elapsed = time.time() - ep_start_time
                logger.info(f"Gym Episode {ep:03d}/{args.episodes} | Steps: {step} | Reward: {total_reward:.2f} | Target Reached: {terminated} | Time: {ep_elapsed:.1f}s")
                
                result = {"status": 0} # Fake success to keep loop moving

            # ----------------------------------------------------
            # PATH B: LEGACY RUN_EPISODE LOOP
            # ----------------------------------------------------
            else:
                reward_kwargs = None
                if args.reward == "cost_aware_v2":
                    reward_kwargs = {"step_penalty": args.step_penalty}

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
                    min_return=args.min_return,
                    state_space=args.state_space,
                    updates_per_step=args.updates_per_step,
                )
            
            # --- Common Checkpoint Logic ---
            if result["status"] != 0:
                logger.error(f"Episode {ep} failed. Stopping training.")
                break
                
            if agent is not None:
                agent.save(str(latest_ckpt_path))
                try:
                    agent.visualize(save_path=str(latest_plot_path), state_space=args.state_space)
                    agent.plot_learning_curve(save_path=str(latest_curve_path))
                except Exception as e:
                    logger.warning(f"Failed to generate visualization or learning curve: {e}")
                
                if ep % args.checkpoint_interval == 0:
                    ckpt_path = checkpoint_folder / f"checkpoint_ep{ep}{file_ext}"
                    plot_path = checkpoint_folder / f"agent_visualization_ep{ep}.png"
                    
                    agent.save(str(ckpt_path))
                    agent.visualize(save_path=str(plot_path), state_space=args.state_space)
                    
                    logger.info(f"💾 Saved interval checkpoint and visualizations for Episode {ep}")

    except KeyboardInterrupt:
        logger.warning("\n⚠️  Training interrupted by user (KeyboardInterrupt).")
    finally:
        if agent is not None:
            agent.save(str(latest_ckpt_path))
            try:
                agent.visualize(save_path=str(latest_plot_path), state_space=args.state_space)
                agent.plot_learning_curve(save_path=str(latest_curve_path))
            except Exception as e:
                pass
                
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