# Sim-Arena: Complete Architecture Guide

> **TL;DR**: A reinforcement learning gym where AI agents (DQN, Epsilon-Greedy, or hand-coded policies) learn to fix Kubernetes resource problems by running simulations, observing pod states, taking actions (like increasing CPU), and getting rewards when pods become healthy.

---

## Table of Contents
1. [What This System Does](#what-this-system-does)
2. [The Big Picture](#the-big-picture)
3. [Directory Structure](#directory-structure)
4. [How Everything Fits Together](#how-everything-fits-together)
5. [Detailed Component Breakdown](#detailed-component-breakdown)
6. [The Agent Loop Flow](#the-agent-loop-flow)
7. [Key Concepts](#key-concepts)
8. [How to Use](#how-to-use)
9. [For Future Development](#for-future-development)

---

## What This System Does

**Problem**: Kubernetes pods fail when they request too much or too little CPU/memory. Figuring out the right resource requests is hard.

**Solution**: Sim-Arena creates a "gym" where an AI agent can:
1. Start a simulation of a failing Kubernetes workload (using SimKube)
2. Observe what's wrong (e.g., "3 pods are pending")
3. Take an action (e.g., "increase CPU requests")
4. Get a reward (shaped or binary based on pod health)
5. Learn over time which actions fix which problems

**Current Stage**: Fully working training loop with DQN and Epsilon-Greedy agents, plus hand-coded fallback policies. Checkpointing, visualization, and learning curve tracking are all supported.

---

## The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│                     TRAINING LOOP                           │
└─────────────────────────────────────────────────────────────┘

for each episode:
  Input: Trace file (broken workload) + Agent (DQN or Greedy)
     ↓
  1. Create Simulation (SimKube starts fake cluster)
     ↓
  2. Wait (duration seconds for pods to fail)
     ↓
  3. Observe (count ready/pending pods)
     ↓
  4. Agent Decision (neural net or epsilon-greedy chooses action)
     ↓
  5. Apply Action (modify trace file)
     ↓
  6. Compute Reward (shaped, base, or max_punish)
     ↓
  7. Agent Learn (update Q-network / value table)
     ↓
  8. Checkpoint & Visualize
     ↓
  Output: Updated agent weights + logs + plots
```

---

## Directory Structure

```
sim-arena/
│
├── runner/                    # Orchestration
│   ├── train.py              # ★ Main training loop (multi-episode, checkpointing)
│   ├── one_step.py           # Run ONE agent step
│   ├── multi_step.py         # Run ONE episode (many steps)
│   ├── policies.py           # Hand-coded fallback policies
│   └── safeguards.py         # Resource limit validation
│
├── agent/                     # ★ Learning agents
│   ├── agent.py              # Agent factory (AgentType enum + unified Agent class)
│   ├── dqn.py                # Deep Q-Network implementation
│   ├── eps_greedy.py         # Epsilon-Greedy tabular agent
│   └── __init__.py
│
├── env/                       # Environment (simulation wrapper)
│   ├── sim_env.py            # Create/delete SimKube simulations
│   ├── __init__.py
│   └── actions/              # Trace mutation operations
│       ├── ops.py            # bump_cpu, bump_mem, scale_replicas
│       └── trace_io.py       # Load/save MessagePack files
│
├── observe/                   # Observation & reward
│   ├── reader.py             # Extract pod states from cluster
│   ├── reward.py             # Compute reward (base / shaped / max_punish)
│   └── print_obs.py          # Debug helper
│
├── ops/                       # Infrastructure/lifecycle
│   ├── hooks.py              # Pre-start/post-end hooks
│   └── preflight.py          # Cluster health checks
│
├── demo/                      # Demo traces & scripts
│   ├── traces/               # 100 generated trace files (.msgpack + .json)
│   ├── generate_traces.py    # Script to make more traces
│   └── *.py                  # Conversion helpers (json2msg, normalize, etc.)
│
├── checkpoints/               # ★ Auto-saved agent checkpoints
│
├── tests/                     # Unit & integration tests
├── runs/                      # Per-step output logs
│   ├── step.jsonl
│   └── summary.json
└── docs/archive/              # Archived design docs
```

---

## Namespaces: `--ns` vs `virtual-default`

SimKube creates pods in a **virtual namespace** derived from the trace: `virtual-<trace-namespace>`. Demo traces use namespace `"default"`, so pods appear in **`virtual-default`**.

- **`--ns`** (e.g. `virtual-default`) is where the *Simulation CR* lives and where preflight checks run.
- **Pods** appear in `virtual-default` (not necessarily in `--ns`).
- To view pods: `kubectl get pods -n virtual-default`
- `make clean-ns` cleans `virtual-default`.

---

## How Everything Fits Together

### The Training Flow (Step by Step)

```
┌──────────────────────────────────────────────────────────────┐
│ USER RUNS:                                                   │
│ nohup python runner/train.py                                 │
│   --trace demo/trace-0001.msgpack                            │
│   --ns virtual-default --deploy web --target 3               │
│   --agent dqn --episodes 50 &                                │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ train.py: SETUP                                              │
│  - Parse args, resolve seed, create checkpoint folder        │
│  - Redirect stdout+stderr → checkpoints/<run>/train.log      │
│  - Write command.txt with full args                          │
│  - Initialize Agent (DQN or Epsilon-Greedy)                  │
│  - Optionally load checkpoint via --load                     │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ train.py: for each episode                                   │
│  → runner/multi_step.py: run_episode()                       │
│     → runner/one_step.py: one_step() × max_steps             │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: PREFLIGHT (ops/preflight.py)                    │
│  - Cluster accessible, SimKube CRDs exist, namespace clean   │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: CREATE SIMULATION (env/sim_env.py)              │
│  - Load trace file → Create SimKube Simulation CR            │
│  - SimKube replays the trace (pods start appearing)          │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: WAIT (duration seconds)                         │
│  - Pods fail because CPU/memory requests are misconfigured   │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: OBSERVE (observe/reader.py)                     │
│  - Query Kubernetes API, count pods:                         │
│    {"ready": 0, "pending": 3, "total": 3}                    │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: AGENT DECISION (agent/agent.py)                 │
│  - DQN: forward pass on obs vector → argmax Q-value          │
│  - Greedy: epsilon-greedy lookup → action index              │
│  - Fallback: policy from runner/policies.py                  │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: APPLY ACTION (env/actions/ops.py)               │
│  - Load trace, modify resources (e.g. CPU 500m → 1000m)      │
│  - Save modified trace                                       │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: COMPUTE REWARD (observe/reward.py)              │
│  - base:       1 if ready==target and pending==0, else 0     │
│  - shaped:     continuous −1 to 1, distance-based            │
│  - max_punish: base + penalties for over-allocation          │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ one_step.py: LOG & CLEANUP                                   │
│  - Write to runs/step.jsonl, runs/summary.json               │
│  - Delete Simulation CR                                      │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ train.py: AGENT LEARN + CHECKPOINT                           │
│  - Agent updates weights (replay buffer + target network)    │
│  - Every step:    save checkpoint_latest + latest plots      │
│  - Every N eps:   save checkpoint_ep<N> + per-ep plot        │
│  - On interrupt:  graceful save in finally block             │
└──────────────────────────────────────────────────────────────┘
```

---

## Detailed Component Breakdown

### 1. `runner/train.py` — **THE MAIN ENTRY POINT**

Orchestrates the full training run across multiple episodes.

**Key responsibilities:**
- Parses all CLI arguments including DQN hyperparameters
- Resolves a random seed (or uses `--seed`) and propagates `base_seed + ep * 1000` per episode for reproducibility
- Creates a timestamped checkpoint folder under `checkpoints/<agent>_<YYYYMMDD_HH>/`
- Redirects OS-level stdout and stderr to `train.log` (works with `nohup`)
- Writes `command.txt` with the exact invocation and all parsed args
- Initializes an `Agent` (DQN or Epsilon-Greedy) and optionally loads from `--load`
- Calls `run_episode()` in a loop; on each episode saves `checkpoint_latest`, `agent_visualization_latest.png`, and `learning_curve_latest.png`
- At `--checkpoint-interval` boundaries, also saves per-episode snapshots
- Gracefully handles `KeyboardInterrupt` and always runs final saves in `finally`

**CLI flags (selected):**

| Flag | Default | Description |
|------|---------|-------------|
| `--trace` | required | Initial trace file |
| `--ns` | required | Kubernetes namespace |
| `--target` | required | Target pod count |
| `--agent` | `greedy` | `greedy` or `dqn` |
| `--episodes` | 200 | Total training episodes |
| `--steps` | 200 | Max steps per episode |
| `--duration` | 90 | Seconds per sim step |
| `--reward` | `shaped` | `base`, `shaped`, or `max_punish` |
| `--Naction` | 4 | Action space size |
| `--checkpoint-interval` | 10 | Save every N episodes |
| `--load` | None | Resume from checkpoint |
| `--save` | None | Extra final save path |
| `--seed` | random | Base random seed |
| `--lr` | 0.001 | DQN learning rate |
| `--gamma` | 0.97 | DQN discount factor |
| `--eps-start` | 1.0 | Initial epsilon |
| `--eps-end` | 0.1 | Final epsilon |
| `--eps-decay` | 1000 | Epsilon decay steps |
| `--buffer-size` | 2000 | Replay buffer capacity |
| `--batch-size` | 32 | DQN minibatch size |
| `--target-update` | 50 | Target network sync frequency |

---

### 2. `agent/agent.py` — **AGENT FACTORY**

Wraps DQN and Epsilon-Greedy behind a single `Agent` interface.

```python
agent = Agent(AgentType.DQN, state_dim=4, n_actions=4, ...)
action_idx = agent.act(obs_vector)
agent.update(state, action, reward, next_state, done)
agent.save("checkpoint.pt")
agent.load("checkpoint.pt")
agent.visualize(save_path="plot.png")
agent.plot_learning_curve(save_path="curve.png")
```

`AgentType` enum values: `DQN`, `EPSILON_GREEDY`

---

### 3. `agent/dqn.py` — **DEEP Q-NETWORK**

Standard DQN with experience replay and a target network.

- State: 4-dimensional vector derived from observation
- Action: discrete index into the action space
- Saves/loads as `.pt` (PyTorch checkpoint)

---

### 4. `agent/eps_greedy.py` — **EPSILON-GREEDY AGENT**

Tabular epsilon-greedy agent for rapid prototyping.

- Saves/loads as `.json`
- Useful for small state spaces or sanity-checking the training loop

---

### 5. `runner/one_step.py` — **SINGLE STEP ORCHESTRATOR**

Runs one complete observe → act → reward cycle.

**Key function**: `one_step(trace_path, namespace, deploy, target, duration, policy_name, agent, reward_name, seed)`

Internally calls `apply_action()` to load, mutate, and save the trace file.

---

### 6. `runner/multi_step.py` — **EPISODE RUNNER**

Calls `one_step()` up to `--steps` times per episode, passing the agent through each step so it can accumulate experience and learn.

---

### 7. `runner/policies.py` — **HAND-CODED FALLBACK POLICIES**

Used when `--agent` is not `dqn` or `greedy`.

Available policies: `noop`, `heuristic`, `random`, `bump_cpu`, `bump_mem`, `scale_replicas`

---

### 8. `env/actions/ops.py` — **TRACE MUTATIONS**

Functions that modify trace files:
- `bump_cpu_small(trace, deploy, step="500m")`
- `bump_mem_small(trace, deploy, step="256Mi")`
- `scale_up_replicas(trace, deploy, delta=1)`

---

### 9. `env/actions/trace_io.py` — **FILE I/O**

- `load_trace(path)` — MessagePack → Python dict
- `save_trace(obj, path)` — Python dict → MessagePack

---

### 10. `observe/reader.py` — **OBSERVATIONS**

```python
observe(namespace, deploy) → {"ready": 2, "pending": 1, "total": 3}
```

---

### 11. `observe/reward.py` — **REWARD FUNCTIONS**

- `base` — Binary (1 if ready==target and pending==0, else 0)
- `shaped` — Continuous (−1 to 1) with distance-based penalties
- `max_punish` — Base + penalties for exceeding CPU/memory/replica limits

---

### 12. `env/sim_env.py` — **SIMULATION WRAPPER**

- `create_simulation(name, trace_path, duration_s, namespace)` — Start SimKube sim
- `delete_simulation(name, namespace)` — Clean up

---

### 13. `ops/preflight.py` — **HEALTH CHECKS**

Verifies cluster connectivity, SimKube CRDs, namespace existence, and no leftover simulations before each step.

---

### 14. `ops/hooks.py` — **LIFECYCLE HOOKS**

Runs shell commands before/after steps (namespace creation, cleanup, etc.)

---

## The Agent Loop Flow

### Single Step

```python
def one_step(trace_path, namespace, deploy, target, duration, agent, reward_name, seed):
    run_hooks("pre_start", namespace)
    sim_uid = create_simulation(name, trace_path, duration, namespace)
    wait_fixed(duration)
    obs = observe(namespace, deploy)          # {"ready": 0, "pending": 3, ...}
    action = agent.act(obs_to_vector(obs))    # integer action index
    out_trace, info = apply_action(trace_path, action, deploy, output_path)
    reward = compute_reward(obs, target, reward_name)
    agent.update(obs, action, reward, next_obs, done)
    write_step_record({...})
    delete_simulation(name, namespace)
    return {"status": 0, "record": {...}}
```

### Full Training Loop

```python
agent = Agent(AgentType.DQN, ...)

for ep in range(1, episodes + 1):
    ep_seed = base_seed + ep * 1000
    result = run_episode(trace_path, namespace, deploy, target,
                         duration, steps, ep_seed, agent_name, reward_name, agent)
    
    agent.save(latest_ckpt_path)
    agent.visualize(save_path=latest_plot_path)
    agent.plot_learning_curve(save_path=latest_curve_path)
    
    if ep % checkpoint_interval == 0:
        agent.save(checkpoint_folder / f"checkpoint_ep{ep}.pt")
```

---

## Key Concepts

### Traces

MessagePack files containing recorded Kubernetes events. Structure:

```json
{
  "events": [{
    "ts": 1234567890,
    "applied_objs": [{
      "kind": "Deployment",
      "metadata": {"name": "web"},
      "spec": {
        "replicas": 3,
        "template": {
          "spec": {
            "containers": [{
              "resources": {
                "requests": {"cpu": "500m", "memory": "256Mi"}
              }
            }]
          }
        }
      }
    }]
  }]
}
```

`demo/traces/` contains 100 pre-generated traces. `demo/generate_traces.py` creates more.

### Observations

```python
obs = {"ready": 2, "pending": 1, "total": 3}
```

### Actions

```python
action = {"type": "bump_cpu_small", "deploy": "web", "step": "500m"}
```

Available types: `noop`, `bump_cpu_small`, `bump_mem_small`, `scale_up_replicas`

### Agents

| Agent | Type | Checkpoint | Best for |
|-------|------|------------|----------|
| `dqn` | Deep Q-Network | `.pt` | Full RL training |
| `greedy` | Epsilon-Greedy | `.json` | Fast prototyping |
| `bump_cpu` etc. | Hand-coded policy | none | Baselines / debugging |

---

## How to Use

### Train a DQN Agent (Background)

```bash
# Clean up any ghost simulations first
pkill -f "train.py.*--ns virtual-default"
kubectl delete simulations.simkube.io --all -n virtual-default

# Start training
nohup python runner/train.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns virtual-default \
  --deploy web \
  --target 3 \
  --agent dqn \
  --episodes 50 &

# Monitor logs
tail -f checkpoints/dqn_<timestamp>/train.log
```

### Resume from a Checkpoint

```bash
nohup python runner/train.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns virtual-default \
  --target 3 \
  --agent dqn \
  --load checkpoints/dqn_20260218_22/checkpoint_ep20.pt \
  --episodes 50 &
```

### Train an Epsilon-Greedy Agent

```bash
nohup python runner/train.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns virtual-default \
  --target 3 \
  --agent greedy \
  --episodes 100 &
```

### Run a Single Step (Debug)

```bash
python runner/one_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns virtual-default \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy bump_cpu

cat runs/step.jsonl
```

### Available Reward Functions

```bash
--reward base        # Binary (0 or 1)
--reward shaped      # Continuous (−1 to 1) with distance penalties
--reward max_punish  # Base + penalties for over-allocation
```

---

## For Future Development

### Adding a New Agent Type

1. Implement your agent class in `agent/`
2. Add a new `AgentType` enum value in `agent/agent.py`
3. Wire up initialization in `train.py`'s argument parsing block

### Enhancing Observations

Add features in `observe/reader.py`:

```python
def observe(namespace, deploy):
    return {
        "ready": ..., "pending": ..., "total": ...,
        "cpu_usage": get_cpu_usage(),       # New!
        "node_capacity": get_node_info(),   # New!
    }
```

Remember to update `state_dim` in `train.py` and the DQN network accordingly.

### Better Rewards

Modify `observe/reward.py`:

```python
def shaped(obs, target_total, T_s):
    if obs["ready"] == target_total and obs["pending"] == 0:
        waste_penalty = calculate_waste(obs)
        return 1.0 - waste_penalty
    return obs["ready"] / target_total - 1.0
```

---

## Quick Reference

### "Where is X happening?"

| What | Where |
|------|-------|
| Training loop + checkpointing | `runner/train.py` |
| Episode runner | `runner/multi_step.py` |
| Single step loop | `runner/one_step.py` |
| DQN agent | `agent/dqn.py` |
| Epsilon-Greedy agent | `agent/eps_greedy.py` |
| Agent factory | `agent/agent.py` |
| Hand-coded policies | `runner/policies.py` |
| Trace modification | `env/actions/ops.py` |
| Observation extraction | `observe/reader.py` |
| Reward calculation | `observe/reward.py` |
| Simulation management | `env/sim_env.py` |
| Cluster health checks | `ops/preflight.py` |

### "What file do I edit to..."

| Goal | File |
|------|------|
| Add a new RL agent | `agent/` + `runner/train.py` |
| Add a new hand-coded policy | `runner/policies.py` |
| Add a new action type | `env/actions/ops.py` + `runner/one_step.py` |
| Change reward function | `observe/reward.py` |
| Add observation features | `observe/reader.py` |
| Change training hyperparameters | `runner/train.py` CLI flags |
| Generate more traces | `demo/generate_traces.py` |

### Data Flow

```
Trace File → Simulation → Cluster → Observation → Agent → Action → Modified Trace
    ↑                                                 ↓
    │                                          Reward + Learn
    └──────────────────────────────────────────────────────────┘
              (Each episode starts from the original trace)
```

---

## Summary

**Sim-Arena is a reinforcement learning gym for Kubernetes resource optimization.**

- **Input**: Trace file with resource problems + an agent (DQN / Greedy / policy)
- **Output**: Trained agent weights + reward history + visualizations
- **Goal**: Learn to fix resource issues through trial and error

**Current state**: Full training loop with DQN and Epsilon-Greedy agents, automatic checkpointing, and learning curve visualization.

**Next steps**: Extend the observation space, tune reward shaping, or plug in more powerful agents (PPO, A2C, etc.) via the `agent/` module. 
