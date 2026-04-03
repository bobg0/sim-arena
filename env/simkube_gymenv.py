import time
import shutil
import hashlib
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import numpy as np
import gymnasium as gym
from gymnasium import spaces

# Import your existing modules
from env.sim_env import SimEnv
from ops.hooks import run_hooks
from observe.reader import observe, current_requests, add_obs_noise
from observe.reward import get_reward
from env.actions.trace_io import load_trace, save_trace
from env.actions.ops import (
    bump_cpu_small, bump_mem_small, reduce_cpu_small,
    reduce_mem_small, scale_up_replicas, scale_down_replicas
)
from runner.safeguards import validate_action
from runner.one_step import wait_for_driver_ready, _get_node_data_dir, _extract_current_state

logger = logging.getLogger("SimKubeEnv")

class SimKubeEnv(gym.Env):
    """Custom Environment that follows gym interface for SimKube."""
    
    etadata = {"render_modes": ["console"], "render_fps": 1}

    def __init__(self, 
                 initial_trace_path: str,
                 namespace: str,
                 deploy: str,
                 target: int,
                 duration: int = 60,
                 reward_name: str = "shaped",
                 reward_kwargs: Optional[dict] = None,
                 obs_noise_scale: float = 0.0,
                 max_steps: int = 10,
                 render_mode: Optional[str] = None):
        super(SimKubeEnv, self).__init__()

        self.render_mode = render_mode
        # Environment configuration
        self.initial_trace_path = initial_trace_path
        self.namespace = namespace
        self.virtual_namespace = "virtual-default"
        self.deploy = deploy
        self.target = target
        self.duration = duration
        self.reward_name = reward_name
        self.reward_kwargs = reward_kwargs or {}
        self.obs_noise_scale = obs_noise_scale
        self.max_steps = max_steps
        
        self.sim_env = SimEnv()
        self.current_step = 0
        self.current_trace_path = None
        
        # Action Space: 7 discrete actions
        self.action_space = spaces.Discrete(7)
        self.action_mapping = {
            0: {"type": "noop"},
            1: {"type": "bump_cpu_small", "step": "500m"},
            2: {"type": "bump_mem_small", "step": "256Mi"},
            3: {"type": "scale_up_replicas", "delta": 1},
            4: {"type": "reduce_cpu_small", "step": "500m"},
            5: {"type": "reduce_mem_small", "step": "256Mi"},
            6: {"type": "scale_down_replicas", "delta": 1},
        }

        # Observation Space: 5-dimensional continuous state space
        self.observation_space = spaces.Box(
            low=0, 
            high=100, # ONLY SUPPORTING 12 FOR NOW  
            shape=(5,), 
            dtype=np.float32
        )

    def reset(self, seed=None, options=None) -> Tuple[np.ndarray, Dict[str, Any]]:
        """Resets the environment to an initial state and returns the initial observation."""
        super().reset(seed=seed)
        self.current_step = 0
        
        # Set up the working directory for traces
        tmp_dir = Path(".tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy the initial trace to be our starting active trace
        self.current_trace_path = str(tmp_dir / f"trace-active-{self._generate_id()}.msgpack")
        shutil.copy2(self.initial_trace_path, self.current_trace_path)

        # Run the initial simulation to observe the starting cluster state
        raw_obs, resources = self._run_simulation_and_observe(self.current_trace_path)
        
        dqn_state = self._compute_dqn_state(raw_obs, resources)
        info = {"raw_obs": raw_obs, "resources": resources, "trace_path": self.current_trace_path}
        
        return np.array(dqn_state, dtype=np.float32), info

    def step(self, action: int) -> Tuple[np.ndarray, float, bool, bool, Dict[str, Any]]:
        """Takes a step in the environment."""
        self.current_step += 1
        
        # 1. Map and Apply the action to the current trace
        action_dict = self.action_mapping[action]
        next_trace_path = str(Path(".tmp") / f"trace-step{self.current_step}-{self._generate_id()}.msgpack")
        
        _, action_info = self._apply_action(self.current_trace_path, action_dict, next_trace_path)
        self.current_trace_path = next_trace_path

        # 2. Run the Kubernetes Simulation with the new trace
        raw_obs, resources = self._run_simulation_and_observe(self.current_trace_path)
        
        # 3. Compute new state representation
        dqn_state = self._compute_dqn_state(raw_obs, resources)
        
        # 4. Compute Reward
        reward_fn = get_reward(self.reward_name, **self.reward_kwargs)
        reward = reward_fn(
            obs=raw_obs,
            target_total=self.target,
            T_s=self.duration,
            resources=resources,
            step_idx=self.current_step,
            action_info=action_info
        )

        # 5. Check Termination Conditions
        ready = raw_obs.get("ready", 0)
        total = raw_obs.get("total", 0)
        pending = raw_obs.get("pending", 0)
        
        terminated = (ready == self.target and total == self.target and pending == 0)
        truncated = self.current_step >= self.max_steps

        info = {
            "raw_obs": raw_obs,
            "resources": resources,
            "action_info": action_info,
            "trace_path": self.current_trace_path
        }

        return np.array(dqn_state, dtype=np.float32), float(reward), terminated, truncated, info

    def _run_simulation_and_observe(self, trace_path: str):
        """Helper to run the SimKube lifecycle and return the observation."""
        sim_name = f"diag-{self._generate_id()}"
        trace_filename = Path(trace_path).name
        cluster_trace_path = f"file:///data/{trace_filename}"
        
        # Pre-start hook
        run_hooks("pre_start", self.virtual_namespace, deploy=self.deploy)
        
        # Copy trace to kind node
        node_data_dir = _get_node_data_dir(self.namespace)
        node_data_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(trace_path, node_data_dir / trace_filename)

        # Execute Simulation
        sim_uid = None
        try:
            sim_uid = self.sim_env.create(
                name=sim_name, trace_path=cluster_trace_path, 
                duration_s=self.duration, namespace=self.namespace
            )
            wait_for_driver_ready(sim_name)
            self.sim_env.wait_fixed(self.duration)
            
            # Smart Polling
            obs = None
            for _ in range(8): 
                try:
                    obs = observe(self.virtual_namespace, self.deploy)
                    if obs and obs.get("total", 0) > 0:
                        break
                except Exception:
                    pass # Ignore API failures
                time.sleep(2)

            if self.obs_noise_scale > 0 and obs is not None:
                obs = add_obs_noise(obs, self.obs_noise_scale, rng=np.random.default_rng())
            
            try:
                resources = current_requests(self.virtual_namespace, self.deploy)
            except Exception as e:
                logger.warning(f"K8s 404: Deployment '{self.deploy}' not found. Defaulting to 0 resources.")
                resources = {"cpu": "0m", "memory": "0Mi", "replicas": 0}
            
        finally:
            if sim_uid:
                try:
                    self.sim_env.delete(name=sim_name, namespace=self.namespace)
                    # Give K8s a few seconds to actually delete the CR 
                    # and release the SimKube lease before the next episode starts.
                    time.sleep(4)
                except Exception as e:
                    logger.warning(f"Failed to delete simulation {sim_name}: {e}")

        # Provide fallback if observation fails
        if obs is None:
            obs = {"ready": 0, "pending": 0, "total": 0}

        return obs, resources

    def _apply_action(self, trace_path: str, action: dict, output_path: str):
        """Applies the modification to the JSON/Msgpack trace file."""
        trace = load_trace(trace_path)
        current_state = _extract_current_state(trace, self.deploy)
        
        is_valid, error_msg = validate_action(action, current_state=current_state)
        if not is_valid:
            save_trace(trace, output_path)
            return output_path, {"changed": False, "action_type": action.get("type"), "blocked": True, "error": error_msg}
        
        action_type = action.get("type", "noop")
        changed = False
        
        if action_type == "noop":
            pass
        elif action_type == "bump_cpu_small":
            changed = bump_cpu_small(trace, self.deploy, step=action.get("step", "500m"))
        elif action_type == "bump_mem_small":
            changed = bump_mem_small(trace, self.deploy, step=action.get("step", "256Mi"))
        elif action_type == "reduce_cpu_small":
            changed = reduce_cpu_small(trace, self.deploy, step=action.get("step", "500m"))
        elif action_type == "reduce_mem_small":
            changed = reduce_mem_small(trace, self.deploy, step=action.get("step", "256Mi"))
        elif action_type == "scale_up_replicas":
            changed = scale_up_replicas(trace, self.deploy, delta=action.get("delta", 1))
        elif action_type == "scale_down_replicas":
            changed = scale_down_replicas(trace, self.deploy, delta=action.get("delta", 1))
            
        save_trace(trace, output_path)
        return output_path, {"changed": changed, "action_type": action_type, "blocked": False}

    def _compute_dqn_state(self, obs, resources):
        """Translates raw kubernetes state into the 5D float vector expected by RL algorithms."""
        cpu_raw = str(resources.get("cpu", "0m"))
        cpu_m = int(cpu_raw[:-1]) if cpu_raw.endswith("m") else int(float(cpu_raw) * 1000)

        mem_raw = str(resources.get("memory", "0Mi"))
        if mem_raw.endswith("Gi"):
            mem_mi = int(float(mem_raw[:-2]) * 1024)
        elif mem_raw.endswith("Mi"):
            mem_mi = int(mem_raw[:-2])
        else:
            mem_mi = int("".join(filter(str.isdigit, mem_raw)) or 0)

        distance = self.target - obs.get("total", 0)
        total = obs.get("total", 0)
        
        replicas = resources.get("replicas", total)
        try:
            replicas = int(replicas) if isinstance(replicas, (int, float)) else int(str(replicas))
        except (ValueError, TypeError):
            replicas = total

        return [
            cpu_m / 4000.0,
            mem_mi / 4096.0,
            obs.get("pending", 0) / 5.0,
            distance / 5.0,
            min(1.0, replicas / 8.0),
        ]
    
    def render(self):
        """Renders the environment to the console."""
        if self.render_mode == "console":
            # Just print the current step and active trace path
            print(f"Step: {self.current_step} | Active Trace: {self.current_trace_path}")

    def _generate_id(self):
        """Generates a deterministic ID based on the environment's random seed."""
        # Use the built-in seeded random generator instead of datetime.now()
        # so that Gymnasium's determinism checks pass.
        val = self.np_random.integers(10000000, 99999999)
        return str(val)