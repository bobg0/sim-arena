# Gymnasium Integration Guide

Sim-Arena provides a standard Gymnasium environment for easy integration with reinforcement learning libraries like Stable Baselines3, Ray RLlib, or custom agents.

## Overview

The `SimKubeEnv` class wraps Sim-Arena's simulation loop in a Gymnasium-compatible interface, allowing you to use standard RL training pipelines.

## Basic Usage

```python
import gymnasium as gym
from env.simkube_gymenv import SimKubeEnv

# Create the environment
env = SimKubeEnv(
    initial_trace_path="demo/trace-0001.msgpack",
    namespace="virtual-default",
    deploy="web",
    target=3,
    duration=40,
    max_steps=10
)

# Standard Gymnasium loop
obs, info = env.reset()
done = False
total_reward = 0

while not done:
    action = env.action_space.sample()  # Random action for demo
    obs, reward, terminated, truncated, info = env.step(action)
    total_reward += reward
    done = terminated or truncated

print(f"Episode finished with total reward: {total_reward}")
```

## Environment Parameters

- `initial_trace_path`: Path to the initial trace file (.msgpack)
- `namespace`: Kubernetes namespace for the simulation
- `deploy`: Deployment name to monitor
- `target`: Target number of ready pods
- `duration`: Seconds to wait after each action for pods to stabilize
- `reward_name`: Reward function ("base", "shaped", "cost_aware_v2", "max_punish")
- `obs_noise_scale`: Add noise to observations (0.0 for deterministic)
- `max_steps`: Maximum steps per episode
- `render_mode`: "console" for text rendering

## Action Space

Discrete space with 7 actions:

| Action | Description |
|--------|-------------|
| 0 | No-op |
| 1 | Bump CPU small (+200m) |
| 2 | Bump CPU large (+1000m) |
| 3 | Bump memory small (+256Mi) |
| 4 | Bump memory large (+1024Mi) |
| 5 | Scale replicas up (+1) |
| 6 | Scale replicas down (-1) |

## Observation Space

Dict space containing pod counts:

```python
{
    "ready": spaces.Discrete(101),    # 0-100 ready pods
    "pending": spaces.Discrete(101),  # 0-100 pending pods
    "total": spaces.Discrete(101)     # 0-100 total pods
}
```

## Reward Functions

- **base**: Binary reward (1.0 if target reached, 0.0 otherwise)
- **shaped**: Continuous reward based on progress toward target
- **cost_aware_v2**: Penalizes resource over-allocation
- **max_punish**: Base reward with hard limits on CPU/memory/replicas

## Integration with RL Libraries

### Stable Baselines3

```python
from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env

# Create vectorized environment
env = make_vec_env(lambda: SimKubeEnv(...), n_envs=4)

# Train PPO agent
model = PPO("MultiInputPolicy", env, verbose=1)
model.learn(total_timesteps=10000)

# Save and load
model.save("ppo_simkube")
model = PPO.load("ppo_simkube")
```

### Custom Agent

```python
class MyAgent:
    def __init__(self, action_space):
        self.action_space = action_space
    
    def act(self, obs):
        # Your policy here
        return self.action_space.sample()

agent = MyAgent(env.action_space)

obs, info = env.reset()
while True:
    action = agent.act(obs)
    obs, reward, terminated, truncated, info = env.step(action)
    if terminated or truncated:
        break
```

## Rendering

Set `render_mode="console"` to print episode progress:

```
Step 0: ready=0, pending=3, total=3 | Action: bump_cpu_small | Reward: 0.0
Step 1: ready=3, pending=0, total=3 | Action: noop | Reward: 1.0
Episode finished!
```

## Notes

- Each episode starts from the initial trace
- Simulations are cleaned up automatically
- Use `virtual-default` namespace for demo traces
- Ensure SimKube cluster is running before use