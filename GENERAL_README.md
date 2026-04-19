# Sim-Arena

A reinforcement learning and LLM benchmarking environment for Kubernetes resource optimization using SimKube simulations.

## What is Sim-Arena?

Sim-Arena is a gym-like environment where AI agents learn to fix Kubernetes pod failures by adjusting resource requests (CPU, memory) and replica counts. It supports:

- **Reinforcement Learning Agents**: Train DQN, Epsilon-Greedy, or custom agents.
- **LLM Benchmarking**: Evaluate large language models (Gemini, Claude) on the same scenarios using MCP tools.
- **Distributed Training**: Scale training across multiple EC2 workers with federated averaging.
- **Gymnasium Integration**: Use standard RL interfaces for easy integration.

The environment simulates failing Kubernetes workloads, observes pod states, applies actions, and provides rewards based on pod health.

## Quick Start

### Prerequisites

- Python 3.8+
- A Kubernetes cluster with SimKube installed (see [Setup Guide](docs/EC2_SETUP_FROM_SCRATCH.md))
- `kubectl` access to the cluster

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/bobg0/sim-arena.git
   cd sim-arena
   ```

2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Verify your cluster:
   ```bash
   make preflight
   ```

### Run a Simple Example

Train a DQN agent on a demo scenario:

```bash
python runner/train.py --trace demo/trace-0001.msgpack --ns virtual-default --target 3 --agent dqn --episodes 10 --steps 5
```

This will:
- Start a simulation of a failing workload
- Train a DQN agent to fix pod issues
- Save checkpoints and logs to `checkpoints/`

### Benchmark an LLM

Evaluate Gemini on the same scenarios:

```bash
python benchmark/run.py --provider gemini --ns virtual-default
```

Requires `GEMINI_API_KEY` environment variable.

## Using Sim-Arena in Your Project

### Gymnasium Interface

Sim-Arena provides a standard Gymnasium environment:

```python
from env.simkube_gymenv import SimKubeEnv

env = SimKubeEnv(
    trace_path="demo/trace-0001.msgpack",
    namespace="virtual-default",
    target_pods=3,
    max_steps=10
)

obs = env.reset()
done = False
while not done:
    action = your_agent.act(obs)  # 0-6: noop, bump_cpu_small, etc.
    obs, reward, done, info = env.step(action)
```

### Custom Agents

Implement the `Agent` interface:

```python
from agent.agent import Agent, AgentType

# For RL agents
agent = Agent(AgentType.DQN, state_dim=5, n_actions=7)

# For LLM agents
agent = Agent(AgentType.LLM, provider="gemini")
```

### Actions

Available actions (7 total):
- 0: No-op
- 1-2: Bump CPU (small/large)
- 3-4: Bump memory (small/large)
- 5-6: Scale replicas (up/down)

### Observations

Dict with pod counts:
```python
{
    "ready": 0,
    "pending": 3,
    "total": 3
}
```

### Rewards

- `base`: 1 if all pods ready and none pending, else 0
- `shaped`: Continuous reward based on progress
- `cost_aware_v2`: Penalizes resource waste
- `max_punish`: Base + hard limits on resources

## Advanced Usage

- **Gymnasium Integration**: [Detailed Guide](docs/GYMNASIUM_INTEGRATION.md)
- **LLM Benchmarking**: [MCP Tools Guide](docs/LLM_BENCHMARKING.md)
- **Distributed Training**: [AWS Setup](docs/AWS_DISTRIBUTED_TRAINING.md)
- **Custom Scenarios**: Generate traces with `demo/generate_traces.py`

## Documentation

- [Developer Guide](DEVELOPER_README.md) - Detailed internals for contributors
- [Worker Protocol](docs/WORKER_PROTOCOL.md) - Distributed training protocol
- [EC2 Setup](docs/EC2_SETUP_FROM_SCRATCH.md) - Cluster setup instructions

## Contributing

See [Developer Guide](DEVELOPER_README.md) for development setup and architecture details.