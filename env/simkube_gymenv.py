import time
import shutil
import hashlib
import random
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

import gymnasium as gym
from gymnasium import spaces
import numpy as np
import uuid

# Import your existing SimEnv and (presumably) your observation/reward logic
from .sim_env import SimEnv
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
# from observe.reader import get_metrics  # Example import based on your repo structure
# from observe.reward import calculate_reward # Example import 

class SimKubeGymEnv(gym.Env):
    """Custom Environment that follows the Gymnasium interface for SimKube."""
    
    metadata = {"render_modes": ["console"]}

    def __init__(self, 
                 initial_trace_path: str,
                 namespace: str,
                 deploy: str,
                 target: int,
                 duration: int = 60,
                 reward_name: str = "shaped",
                 reward_kwargs: Optional[dict] = None,
                 obs_noise_scale: float = 0.0,
                 max_steps: int = 10):
        super(SimKubeEnv, self).__init__()
                 '''(self, 
                 trace_path: str, 
                 namespace="simkube", 
                 duration_s=60, 
                 render_mode=None):
        super().__init__()
        self.namespace = namespace
        self.duration_s = duration_s
        self.trace_path = trace_path
        self.render_mode = render_mode'''
        
        # Initialize your core Kubernetes interaction class
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

        self.config = config
        self.sim_env = SimEnv()
        self.sim_handler = SimEnv() # ITS ONE OR THE OTHER IDK
        self.current_sim_name = None
        self.current_step = 0
        self.current_trace_path = None

        self.reward_fn = get_reward(config.get("reward_type", "cost_aware_v2"))

        # ---------------------------------------------------------
        # TODO: Define your Action and Observation Spaces
        # ---------------------------------------------------------
        # Action Space: 0: No-op, 1: +CPU, 2: -CPU, 3: +Mem, 4: -Mem, 5: +Repl, 6: -Repl
        self.action_space = spaces.Discrete(7)

        self.action_mapping = { # I DO NOT KNOW IF I NEED THIS
            0: {"type": "noop"},
            1: {"type": "bump_cpu_small", "step": "500m"},
            2: {"type": "bump_mem_small", "step": "256Mi"},
            3: {"type": "scale_up_replicas", "delta": 1},
            4: {"type": "reduce_cpu_small", "step": "500m"},
            5: {"type": "reduce_mem_small", "step": "256Mi"},
            6: {"type": "scale_down_replicas", "delta": 1},
        }
        
        # Example: If your observation is an array of 5 cluster metrics (CPU, Mem, etc.)
        # self.observation_space = spaces.Box(low=0.0, high=np.inf, shape=(5,), dtype=np.float32)

        self.observation_space = spaces.Dict({
            "ready": spaces.Discrete(100),
            "pending": spaces.Discrete(100),
            "total": spaces.Discrete(100),
            "cpu_millicores": spaces.Box(low=0, high=10000, shape=(1,), dtype=np.int32),
            "memory_bytes": spaces.Box(low=0, high=10**12, shape=(1,), dtype=np.int64),
            "replicas": spaces.Discrete(50)
        })

        self.current_trace_obj = None # Will hold the trace mapping
        self.simulation_handle = None

    def reset(self, seed=None, options=None):
        """Resets the environment to an initial state and returns the initial observation."""
        super().reset(seed=seed)
        self.current_step = 0

        # Set up the working directory for traces
        tmp_dir = Path(".tmp")
        tmp_dir.mkdir(parents=True, exist_ok=True)
        
        # Copy the initial trace to be our starting active trace
        self.current_trace_path = str(tmp_dir / f"trace-active-{self._generate_id()}.msgpack")
        shutil.copy2(self.initial_trace_path, self.current_trace_path)
        
        # 1. Clean up the previous simulation if it exists
        if self.current_sim_name:
            self.sim_env.delete(name=self.current_sim_name, namespace=self.namespace)

        # 2. Create a unique name for the new simulation run
        self.current_sim_name = f"sim-{uuid.uuid4().hex[:8]}"
        
        # 3. Start the simulation in the cluster
        self.sim_env = self.sim_env.create(
            name=self.current_sim_name,
            trace_path=self.trace_path,
            namespace=self.namespace,
            duration_s=self.duration_s
        )
        
        # 4. Wait a moment for the cluster to initialize the simulation pods
        self.sim_env.wait_fixed(5) 
        
        # 5. Fetch the initial state of the cluster
        observation = self._get_obs()
        info = self._get_info()
        
        return observation, info

    def step(self, action):
        """Applies an action, advances the environment, and returns the new state."""
        
        # 1. Apply the action to the Kubernetes cluster
        # e.g., if action == 0: scale_down(), elif action == 1: scale_up()
        self._apply_action(action)

        # 1. Apply Action using your operations
        if action == 1: bump_cpu_small(self.current_trace_obj, deploy)
        elif action == 2: reduce_cpu_small(self.current_trace_obj, deploy)
        elif action == 3: bump_mem_small(self.current_trace_obj, deploy)
        elif action == 4: reduce_mem_small(self.current_trace_obj, deploy)
        elif action == 5: scale_up_replicas(self.current_trace_obj, deploy)
        elif action == 6: scale_down_replicas(self.current_trace_obj, deploy)
        
        # 2. Let the simulation run for a timestep
        # If duration_s in __init__ is the total simulation length, you might 
        # instead want a smaller step duration here.
        step_duration = 10 
        self.sim_env.wait_fixed(step_duration)

        self.sim_handler.wait_fixed(self.config["step_duration"])
        
        # 3. Gather new metrics
        observation = self._get_obs()
        
        # 4. Calculate the reward based on the new state
        reward = self._calculate_reward(observation)

        # 4. Calculate reward
        resources = current_requests(self.config["namespace"], deploy)
        reward = self.reward_fn(
            obs=obs,
            target_total=self.config["target_pods"],
            T_s=self.config["step_duration"],
            resources=resources
        )
        
        # 5. Determine if the episode is done (e.g., trace is finished, or cluster crashed)
        terminated = self._check_terminated(observation)
        truncated = False # Set to True if hitting a hard time limit
        
        info = self._get_info()
        
        return observation, reward, terminated, truncated, info

    def render(self):
        """Visualizes the environment."""
        if self.render_mode == "console":
            print(f"Current Sim: {self.current_sim_name} | Status: Running")

    def close(self):
        """Cleans up cluster resources when the environment is closed."""
        if self.current_sim_name:
            self.sim_env.delete(name=self.current_sim_name, namespace=self.namespace)
            self.current_sim_name = None

    # --- Helper Methods to be filled in with your specific logic ---

    def _get_obs(self):
        # `observe.reader` logic here to pull metrics from K8s/Prometheus
        # return a numpy array that matches self.observation_space
        # return np.zeros(5, dtype=np.float32)

        # Use your existing observation logic
        pod_stats = observe(self.config["namespace"], self.config["deployment_name"])
        res_stats = current_requests(self.config["namespace"], self.config["deployment_name"])
        
        # Format as defined in self.observation_space
        return {
            "ready": pod_stats["ready"],
            "pending": pod_stats["pending"],
            "total": pod_stats["total"],
            "cpu_millicores": np.array([res_stats.get("cpu", 0)], dtype=np.int32),
            "memory_bytes": np.array([res_stats.get("memory", 0)], dtype=np.int64),
            "replicas": res_stats["replicas"]
        }

    def _apply_action(self, action):
        # Use your `env.actions.ops` logic here to interact with K8s
        pass

    def _calculate_reward(self, observation):
        # Use your `observe.reward` logic here
        return 0.0

    def _check_terminated(self, observation):
        # Logic to decide if the simulation trace is complete
        return False
        
    def _get_info(self):
        # Optional dictionary for debugging metrics
        return {"simulation_name": self.simulation_handle.get("name") if self.simulation_handle else None}
    
    def close(self):
        # Ensure simulation is deleted from the cluster on exit
        if self.simulation_handle:
            self.sim_handler.delete(handle=self.simulation_handle)