# Sim-Arena: Complete Architecture Guide

> **TL;DR**: This system lets an AI agent learn to fix Kubernetes resource problems by running simulations, observing what goes wrong, taking actions (like increasing CPU), and getting rewards when pods become healthy.

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
4. Get a reward (1 if all pods healthy, 0 if not)
5. Learn over time which actions fix which problems

**Current Stage**: We have a working loop with hand-coded policies. Next step: plug in learning agents (PPO, DQN, etc.)

---

## The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│                     ONE AGENT STEP                           │
└─────────────────────────────────────────────────────────────┘

Input: Trace file (broken workload)
   ↓
1. Create Simulation (SimKube starts fake cluster)
   ↓
2. Wait (60-120 seconds for pods to fail)
   ↓
3. Observe (count ready/pending pods)
   ↓
4. Policy Decision (agent chooses action)
   ↓
5. Apply Action (modify trace file)
   ↓
6. Compute Reward (did it work?)
   ↓
7. Log Results
   ↓
Output: Modified trace file + reward + logs
```

---

## Directory Structure

```
sim-arena/
│
├── runner/                    # Agent orchestration
│   ├── one_step.py           # Main loop (run ONE agent step)
│   ├── policies.py           # Hand-coded policies (6 policies)
│   └── multi_step.py         # Run MANY steps (episodes)
│
├── env/                       # Environment (simulation wrapper)
│   ├── sim_env.py            # Create/delete SimKube simulations
│   ├── __init__.py           # Convenience functions
│   └── actions/              # Trace mutation operations
│       ├── ops.py            # bump_cpu, bump_mem, scale_replicas
│       └── trace_io.py       # Load/save MessagePack files
│
├── observe/                   # Observation & reward
│   ├── reader.py             # Extract pod states from cluster
│   └── reward.py             # Compute reward (binary: success/fail)
│
├── ops/                       # Infrastructure/lifecycle
│   ├── hooks.py              # Pre-start/post-end hooks
│   └── preflight.py          # Cluster health checks
│
├── demo/                      # Demo traces & scripts
│   ├── traces/               # 100 generated trace files
│   └── generate_traces.py   # Script to make more traces
│
├── tests/                     # Unit & integration tests
│
└── runs/                      # Output logs
    ├── step.jsonl            # One line per step
    └── summary.json          # Aggregated stats
```

---

## How Everything Fits Together

### The Flow (Step by Step)

```
┌──────────────────────────────────────────────────────────────┐
│ USER RUNS:                                                    │
│ python runner/one_step.py --trace demo/trace-0001.msgpack   │
│   --ns test-ns --deploy web --target 3 --duration 60        │
│   --policy bump_cpu                                          │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 1. PREFLIGHT (ops/preflight.py)                             │
│    - Check cluster is accessible                             │
│    - Verify SimKube CRDs exist                              │
│    - Ensure namespace is clean                              │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 2. CREATE SIMULATION (env/sim_env.py)                       │
│    - Load trace file (demo/trace-0001.msgpack)              │
│    - Create SimKube Simulation CR in cluster                │
│    - SimKube replays the trace (pods start appearing)       │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 3. WAIT (60 seconds)                                         │
│    - Let the simulation run                                  │
│    - Pods fail because CPU requests are too high            │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 4. OBSERVE (observe/reader.py)                              │
│    - Query Kubernetes API                                    │
│    - Count pods: ready=0, pending=3, total=3                │
│    - Return observation dict                                 │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 5. POLICY DECISION (runner/policies.py)                     │
│    - Get policy: policy = POLICIES["bump_cpu"]              │
│    - Call: action = policy(obs, "web")                      │
│    - Returns: {"type": "bump_cpu_small", "deploy": "web"}   │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 6. APPLY ACTION (runner/one_step.py + env/actions/ops.py)  │
│    - Load trace file                                         │
│    - Modify: bump CPU from 500m → 1000m                     │
│    - Save modified trace to .tmp/trace-next.msgpack         │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 7. COMPUTE REWARD (observe/reward.py)                       │
│    - Check: ready==3 and pending==0?                         │
│    - No → reward = 0                                         │
│    - (Next episode will use modified trace and might work!)  │
└──────────────────────────────────────────────────────────────┘
                           ↓
┌──────────────────────────────────────────────────────────────┐
│ 8. LOG & CLEANUP                                             │
│    - Write step record to runs/step.jsonl                    │
│    - Update runs/summary.json                                │
│    - Delete Simulation CR                                    │
│    - Done!                                                   │
└──────────────────────────────────────────────────────────────┘
```

---

## Detailed Component Breakdown

### 1. `runner/one_step.py` (263 lines) - **THE MAIN FILE**

**What it does**: Orchestrates ONE complete agent step

**Key function**: `one_step(trace_path, namespace, deploy, target, duration, policy_name)`

**What happens inside:**
1. Loads policy from `policies.py`
2. Runs preflight checks
3. Creates simulation
4. Waits for specified duration
5. Observes cluster state
6. Gets action from policy
7. Applies action to trace file
8. Computes reward
9. Logs everything
10. Cleans up

**Internal helper**: `apply_action()` - loads trace, modifies it, saves it

**When to edit this file:**
- Changing the agent loop flow
- Adding new logging
- Modifying how actions are applied

---

### 2. `runner/policies.py` (59 lines) - **POLICIES/AGENTS**

**What it does**: Contains hand-coded policies (agents)

**Current policies:**
- `noop` - Do nothing
- `heuristic` - If pending > 0, bump CPU
- `random` - Random action
- `bump_cpu` - Always increase CPU
- `bump_mem` - Always increase memory
- `scale_replicas` - Always add replicas

**Structure:**
```python
def policy_bump_cpu(obs: dict, deploy: str) -> dict:
    return {"type": "bump_cpu_small", "deploy": deploy}

POLICY_REGISTRY = {
    "bump_cpu": policy_bump_cpu,
    ...
}
```

**When to edit this file:**
- Adding new hand-coded policies
- Testing different strategies

**For learning agents:**
This file will be replaced/augmented with PPO/DQN agents that return actions

---

### 3. `env/actions/ops.py` (195 lines) - **TRACE MUTATIONS**

**What it does**: The actual functions that modify trace files

**Key functions:**
- `bump_cpu_small(trace, deploy, step="500m")` - Increase CPU
- `bump_mem_small(trace, deploy, step="256Mi")` - Increase memory
- `scale_up_replicas(trace, deploy, delta=1)` - Add replicas

**How it works:**
1. Navigate trace structure (events → applied_objs → Deployment)
2. Find the target deployment
3. Modify spec.template.spec.containers[0].resources.requests
4. Return True if changed, False if deployment not found

**When to edit this file:**
- Adding new action types (e.g., reduce CPU, set limits)
- Changing resource increment amounts
- Debugging trace mutations

---

### 4. `env/actions/trace_io.py` (69 lines) - **FILE I/O**

**What it does**: Load/save MessagePack trace files

**Key functions:**
- `load_trace(path)` - Deserialize MessagePack → Python dict
- `save_trace(obj, path)` - Serialize Python dict → MessagePack

**When to edit this file:**
- Rarely (it just works)
- Only if changing trace format

---

### 5. `observe/reader.py` (106 lines) - **OBSERVATIONS**

**What it does**: Query Kubernetes cluster and extract pod states

**Key function:**
```python
observe(namespace, deploy) → {"ready": 2, "pending": 1, "total": 3}
```

**How it works:**
1. Query Kubernetes API for pods in namespace
2. Filter by deployment name
3. Check pod status (Running + all containers ready = "ready")
4. Count ready, pending, total

**When to edit this file:**
- Adding new observation features (CPU usage, node info, etc.)
- Changing observation space

---

### 6. `observe/reward.py` (25 lines) - **REWARD FUNCTION**

**What it does**: Decide if the agent succeeded

**Current logic:**
```python
def reward(obs, target_total, T_s):
    if obs["ready"] == target_total and obs["pending"] == 0:
        return 1  # Success!
    else:
        return 0  # Failed
```

**Why it's separate:**
- Will be used by external learning agents
- May become more complex (gradual rewards, penalties, etc.)
- Conceptually a separate concern

**When to edit this file:**
- Changing reward structure (gradual, shaped, etc.)
- Adding penalties for over-allocation
- Experimenting with different reward signals

---

### 7. `env/sim_env.py` (156 lines) - **SIMULATION WRAPPER**

**What it does**: Create/delete SimKube simulations

**Key functions:**
- `create_simulation(name, trace_path, duration_s, namespace)` - Start simulation
- `delete_simulation(name, namespace)` - Clean up

**How it works:**
1. Create Kubernetes CR of kind `Simulation`
2. SimKube controller picks it up and replays the trace
3. Pods appear in the cluster as if it were real

**When to edit this file:**
- Rarely (it's a thin wrapper around SimKube)
- Only if changing how simulations are configured

---

### 8. `ops/preflight.py` (163 lines) - **HEALTH CHECKS**

**What it does**: Verify cluster is ready before running

**Checks:**
- Can connect to Kubernetes
- SimKube CRDs exist
- Namespace exists
- No leftover simulations

**When to edit this file:**
- Adding new preflight checks
- Improving error messages

---

### 9. `ops/hooks.py` (99 lines) - **LIFECYCLE HOOKS**

**What it does**: Run commands before/after steps

**Example use cases:**
- Create namespace if missing
- Clean up old simulations
- Reset cluster state

**When to edit this file:**
- Adding new hooks (pre_start, post_end)
- Automating setup/teardown

---

## The Agent Loop Flow

### Single Step (one_step.py)

```python
def one_step(trace_path, namespace, deploy, target, duration, policy_name):
    # 1. Setup
    run_hooks("pre_start", namespace)
    
    # 2. Create simulation
    sim_uid = create_simulation(name, trace_path, duration, namespace)
    
    # 3. Wait
    wait_fixed(duration)
    
    # 4. Observe
    obs = observe(namespace, deploy)  # {"ready": 0, "pending": 3, ...}
    
    # 5. Policy
    policy = get_policy(policy_name)
    action = policy(obs, deploy)      # {"type": "bump_cpu_small", "deploy": "web"}
    
    # 6. Apply action
    out_trace_path, info = apply_action(trace_path, action, deploy, output_path)
    
    # 7. Reward
    reward = compute_reward(obs, target, duration)  # 0 or 1
    
    # 8. Log
    write_step_record({...})
    
    # 9. Cleanup
    delete_simulation(name, namespace)
    
    return {"status": 0, "record": {...}}
```

### Multi-Episode Loop (multi_step.py)

```python
for episode in range(num_episodes):
    # Use output trace from previous episode as input
    result = one_step(current_trace, ...)
    current_trace = result["record"]["trace_out"]
    
    if result["record"]["reward"] == 1:
        print("Success!")
        break
```

---

## Key Concepts

### 1. Traces

**What they are:** MessagePack files containing recorded Kubernetes events

**Structure:**
```json
{
  "events": [
    {
      "ts": 1234567890,
      "applied_objs": [
        {
          "kind": "Deployment",
          "metadata": {"name": "web"},
          "spec": {
            "replicas": 3,
            "template": {
              "spec": {
                "containers": [{
                  "name": "app",
                  "resources": {
                    "requests": {
                      "cpu": "500m",
                      "memory": "256Mi"
                    }
                  }
                }]
              }
            }
          }
        }
      ]
    }
  ]
}
```

**Why MessagePack?** Faster and smaller than JSON

**Where they come from:**
- `demo/traces/` - 100 pre-generated traces with resource problems
- `demo/generate_traces.py` - Script to generate more

### 2. Observations

**What they are:** Dictionary of pod states

**Example:**
```python
obs = {
    "ready": 2,      # Pods Running + all containers ready
    "pending": 1,    # Pods in Pending state
    "total": 3,      # Total pods
}
```

**Future extensions:**
- CPU/memory usage
- Node information
- Event logs

### 3. Actions

**What they are:** Dictionary describing what to do

**Example:**
```python
action = {
    "type": "bump_cpu_small",
    "deploy": "web",
    "step": "500m"  # optional
}
```

**Available types:**
- `noop` - Do nothing
- `bump_cpu_small` - Increase CPU
- `bump_mem_small` - Increase memory
- `scale_up_replicas` - Add replicas

### 4. Policies

**What they are:** Functions that map observations → actions

**Signature:**
```python
def policy(obs: dict, deploy: str) -> dict:
    # Your logic here
    return action_dict
```

**Current policies:** Hand-coded heuristics
**Future:** PPO, DQN, A3C agents

---

## How to Use

### Basic Run

```bash
cd sim-arena

# Run one step with bump_cpu policy
python runner/one_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy bump_cpu

# Check results
cat runs/step.jsonl
cat runs/summary.json
```

### Available Policies

```bash
--policy noop           # Do nothing
--policy heuristic      # If pending, bump CPU
--policy random         # Random action
--policy bump_cpu       # Always bump CPU
--policy bump_mem       # Always bump memory
--policy scale_replicas # Always add replicas
```

### Run Multiple Episodes

```bash
python runner/multi_step.py \
  --trace demo/traces/trace-0001.msgpack \
  --ns test-ns \
  --deploy web \
  --target 3 \
  --duration 60 \
  --policy heuristic \
  --episodes 10
```

---

## For Future Development

### Plugging in Learning Agents

Replace `runner/policies.py` with your agent:

```python
# Your agent file
class PPOAgent:
    def __init__(self):
        self.model = load_model()
    
    def get_action(self, obs: dict, deploy: str) -> dict:
        # Neural network decides action
        action_type = self.model.predict(obs)
        return {"type": action_type, "deploy": deploy}

# In one_step.py
agent = PPOAgent()
action = agent.get_action(obs, deploy)
```

### Extending the Action Space

Add new actions in `env/actions/ops.py`:

```python
def reduce_cpu(obj, deploy, step="500m"):
    # Implementation
    ...

def set_cpu_limit(obj, deploy, limit="2000m"):
    # Implementation
    ...
```

Then update `runner/one_step.py` `apply_action()`:

```python
elif action_type == "reduce_cpu":
    changed = reduce_cpu(trace, deploy, ...)
```

### Enhancing Observations

Add more info in `observe/reader.py`:

```python
def observe(namespace, deploy):
    return {
        "ready": ...,
        "pending": ...,
        "total": ...,
        "cpu_usage": get_cpu_usage(),      # New!
        "node_capacity": get_node_info(),  # New!
    }
```

### Better Rewards

Modify `observe/reward.py`:

```python
def reward(obs, target_total, T_s):
    if obs["ready"] == target_total and obs["pending"] == 0:
        # Penalize for over-allocation
        waste_penalty = calculate_waste(obs)
        return 1.0 - waste_penalty
    else:
        # Gradual reward for progress
        return obs["ready"] / target_total
```

---

## Questions?

### "Where is X happening?"

| What | Where |
|------|-------|
| Main agent loop | `runner/one_step.py` |
| Policy selection | `runner/policies.py` |
| Trace modification | `env/actions/ops.py` |
| Observation extraction | `observe/reader.py` |
| Reward calculation | `observe/reward.py` |
| Simulation management | `env/sim_env.py` |
| Cluster health checks | `ops/preflight.py` |

### "What file do I edit to..."

| Goal | File to Edit |
|------|-------------|
| Add a new policy | `runner/policies.py` |
| Add a new action type | `env/actions/ops.py` + `runner/one_step.py` |
| Change reward function | `observe/reward.py` |
| Add observation features | `observe/reader.py` |
| Modify agent loop | `runner/one_step.py` |
| Generate more traces | `demo/generate_traces.py` |

### "How does data flow?"

```
Trace File → Simulation → Cluster → Observation → Policy → Action → Modified Trace
    ↑                                                                        ↓
    └────────────────────────────────────────────────────────────────────────┘
                         (Next episode uses modified trace)
```

---

## Summary

**Sim-Arena is a reinforcement learning gym for Kubernetes resource optimization.**

- **Input**: Trace file with resource problems
- **Output**: Modified trace + reward signal
- **Goal**: Learn to fix resource issues through trial and error

**Current state**: Working loop with hand-coded policies
**Next step**: Plug in learning agents (PPO, DQN, etc.)

The system is now **simple, direct, and ready for ML agents**! 🚀
