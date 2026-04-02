# Sim-Arena

**Canonical README** for this codebase inside the [`clinic_ACRL`](../README.md) monorepo — use this file for setup, training, benchmarks, and operations.

> **TL;DR**: A reinforcement learning gym where AI agents (DQN, Epsilon-Greedy, or hand-coded policies) learn to fix Kubernetes resource problems by running simulations, observing pod states, taking actions (like increasing CPU), and getting rewards when pods become healthy. Now also supports **LLM benchmarking** — Gemini and Claude models can be evaluated on the same scenarios using live Kubernetes tool access via MCP.

---

## Repository context (`clinic_ACRL`)

This folder is part of the **`clinic_ACRL`** monorepo (sibling trees: `simkube/`, `isengard/`, optional `sim-arena-backup/`). For a **single document** that explains the whole workspace, distributed jobs, EC2, and what is still stubbed, read **[`../PROJECT_OUTLINE_CHATGPT.md`](../PROJECT_OUTLINE_CHATGPT.md)** from the repo root.

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
9. [LLM Benchmarking](#llm-benchmarking)
10. [Distributed training (S3 workers and EC2)](#distributed-training-s3-workers-and-ec2)
11. [For Future Development](#for-future-development)

---

## What This System Does

**Problem**: Kubernetes pods fail when they request too much or too little CPU/memory. Figuring out the right resource requests is hard.

**Solution**: Sim-Arena creates a "gym" where an AI agent can:
1. Start a simulation of a failing Kubernetes workload (using SimKube)
2. Observe what's wrong (e.g., "3 pods are pending")
3. Take an action (e.g., "increase CPU requests")
4. Get a reward (shaped or binary based on pod health)
5. Learn over time which actions fix which problems

**RL Training**: Fully working training loop with DQN and Epsilon-Greedy agents, plus hand-coded fallback policies. Checkpointing, visualization, and learning curve tracking are all supported.

**LLM Benchmarking**: LLM agents (Gemini, Claude) can be evaluated on the same scenarios. They use MCP tools to query the live cluster — pod states, events, logs, deployment config — before deciding on an action. Both RL and LLM agents share the same action space and reward functions.

---

## The Big Picture

```
┌─────────────────────────────────────────────────────────────┐
│                     TRAINING LOOP (RL)                      │
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
  6. Compute Reward (shaped, base, cost_aware_v2, or max_punish)
     ↓
  7. Agent Learn (update Q-network / value table)
     ↓
  8. Checkpoint & Visualize
     ↓
  Output: Updated agent weights + logs + plots

┌─────────────────────────────────────────────────────────────┐
│                  BENCHMARK LOOP (LLM)                       │
└─────────────────────────────────────────────────────────────┘

for each scenario:
  Input: Trace file + LLM provider (Gemini / Claude)
     ↓
  1. Create Simulation (same SimKube infrastructure)
     ↓
  2. Observe base pod state
     ↓
  3. LLM queries MCP tools (get_pods, get_events, describe_deployment, get_pod_logs)
     ↓
  4. LLM decides action → same ACTION_SPACE as RL agents
     ↓
  5. Apply Action + Compute Reward (same functions)
     ↓
  6. Record metrics (steps, reward, tool calls, latency, solved)
     ↓
  Output: report.json + report.md in benchmark/results/
```

---

## Directory Structure

```
sim-arena/
│
├── runner/                    # Orchestration
│   ├── train.py              # ★ Main RL training loop (multi-episode, checkpointing)
│   ├── one_step.py           # Run ONE agent step (RL or LLM)
│   ├── multi_step.py         # Run ONE episode (many steps)
│   ├── policies.py           # Hand-coded fallback policies
│   └── safeguards.py         # Resource limit validation
│
├── agent/                     # ★ All agent implementations
│   ├── agent.py              # Agent factory (AgentType enum + unified Agent class)
│   ├── dqn.py                # Deep Q-Network implementation
│   ├── eps_greedy.py         # Epsilon-Greedy tabular agent
│   ├── llm_agent.py          # ★ LLM agent (provider-agnostic, uses MCP tools)
│   ├── prompt_builder.py     # Builds system + user prompts from obs dict
│   ├── action_parser.py      # Parses LLM JSON response → action index
│   └── providers/            # ★ LLM provider implementations
│       ├── base.py           # LLMProvider abstract base class
│       ├── gemini_provider.py  # Google Gemini (google-genai SDK)
│       └── anthropic_provider.py  # Anthropic Claude
│
├── sim_mcp/                   # ★ MCP server: Kubernetes observability tools
│   ├── server.py             # FastMCP server (runs as stdio subprocess)
│   ├── client.py             # MCPClientSync wrapper used by LLMAgent
│   └── tools/
│       ├── _k8s.py           # Shared Kubernetes client loader
│       ├── pods.py           # get_pods(namespace)
│       ├── deployments.py    # describe_deployment(namespace, deploy)
│       ├── events.py         # get_events(namespace, deploy, last_n)
│       └── logs.py           # get_pod_logs(namespace, pod_name, tail_lines)
│
├── benchmark/                 # ★ LLM benchmark harness
│   ├── run.py                # Entry point: python benchmark/run.py --provider gemini
│   ├── metrics.py            # Per-step + per-episode metric collection & reports
│   └── scenarios/
│       ├── index.json        # Scenario registry (name, trace, target, problem_type)
│       └── __init__.py       # load_scenarios() helper
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
├── checkpoints/               # ★ Auto-saved RL agent checkpoints
├── tests/                     # Unit & integration tests
├── runs/                      # Per-step output logs (step.jsonl, summary.json)
├── .env.example               # API key template — copy to .env and fill in
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

### The RL Training Flow (Step by Step)

```
USER RUNS:
  python runner/train.py --trace demo/trace-0001.msgpack --ns virtual-default --agent dqn

train.py: SETUP
  - Parse args, resolve seed, create checkpoint folder
  - Redirect stdout+stderr → checkpoints/<run>/train.log
  - Initialize Agent (DQN or Epsilon-Greedy)

train.py: for each episode
  → runner/multi_step.py: run_episode()
     → runner/one_step.py: one_step() × max_steps

one_step.py:
  1. PREFLIGHT      — cluster accessible, SimKube CRDs exist, namespace clean
  2. CREATE SIM     — SimKube Simulation CR created, pods start appearing
  3. WAIT           — duration seconds for pod state to stabilise
  4. OBSERVE        — {"ready": 0, "pending": 3, "total": 3}
  5. AGENT DECISION — DQN forward pass or epsilon-greedy lookup → action index
  6. APPLY ACTION   — load trace, mutate resources, save trace
  7. COMPUTE REWARD — shaped / base / cost_aware_v2 / max_punish
  8. LOG & CLEANUP  — write step.jsonl, delete Simulation CR

train.py: AGENT LEARN + CHECKPOINT
  - Update Q-network / replay buffer
  - Save checkpoint_latest + learning curve plots
  - Save checkpoint_epN every N episodes
```

### The LLM Benchmark Flow

```
USER RUNS:
  python benchmark/run.py --provider gemini --ns virtual-default

benchmark/run.py:
  1. Load scenarios from benchmark/scenarios/index.json
  2. Start MCP server subprocess (sim_mcp/server.py via MCPClientSync)
  3. For each scenario:
       → run_episode() from runner/multi_step.py  [unchanged from RL]
          → one_step() with agent_name="llm"
             → LLMAgent.act(obs, namespace, deploy, ...)
                1. Build prompt from obs + scenario context
                2. Call LLM API with 4 MCP tools attached
                3. LLM calls tools 0–N times autonomously:
                     get_pods / describe_deployment / get_events / get_pod_logs
                4. LLM returns JSON → action index (same ACTION_SPACE)
  4. Record: steps_to_solve, reward, tool_calls, latency, solved
  5. Write benchmark/results/<timestamp>/report.json + report.md
```

---

## Detailed Component Breakdown

### RL Components

#### `runner/train.py` — Main RL Entry Point

Orchestrates the full training run across multiple episodes.

| Flag | Default | Description |
|------|---------|-------------|
| `--trace` | required | Initial trace file or directory |
| `--ns` | required | Kubernetes namespace |
| `--target` | required | Target pod count |
| `--agent` | `greedy` | `greedy`, `dqn`, or `random` |
| `--episodes` | 200 | Total training episodes |
| `--steps` | 200 | Max steps per episode |
| `--duration` | 40 | Seconds per sim step |
| `--reward` | `shaped` | `base`, `shaped`, `cost_aware_v2`, or `max_punish` |
| `--Naction` | 4 | Action space size |
| `--checkpoint-interval` | 10 | Save every N episodes |
| `--load` | None | Resume from checkpoint |
| `--save` | None | Extra final save path |
| `--seed` | random | Base random seed |
| `--lr` | 0.001 | DQN learning rate |
| `--gamma` | 0.97 | DQN discount factor |
| `--step-penalty` | 0 | Per-step penalty for `cost_aware_v2` |

#### `agent/agent.py` — Agent Factory

Wraps all agent types behind a single `Agent` interface.

```python
agent = Agent(AgentType.DQN, state_dim=5, n_actions=7, ...)
action_idx = agent.act(obs_vector)
agent.update(state, action, reward, next_state, done)
agent.save("checkpoint.pt")
agent.load("checkpoint.pt")
```

`AgentType` enum values: `DQN`, `EPSILON_GREEDY`, `RANDOM`, `LLM`

#### `observe/reward.py` — Reward Functions

- `base` — Binary (1 if ready==target and pending==0, else 0)
- `shaped` — Continuous (−1 to 1) with distance-based penalties
- `cost_aware_v2` — All negative except 0 at goal; health + cost shaping; penalises blocked actions
- `max_punish` — Base + penalties for exceeding CPU/memory/replica limits

#### `runner/safeguards.py` — Resource Limits

Blocks actions that would exceed safe limits: CPU max 16000m, memory max 32Gi, replicas max 100. Prevents the agent from allocating absurd resources.

---

### LLM Benchmark Components

#### `sim_mcp/server.py` — MCP Server

FastMCP server exposing four Kubernetes observability tools. Runs as a stdio subprocess started automatically by `MCPClientSync`.

#### `sim_mcp/tools/` — K8s Tools

| Tool | What it returns | When to use |
|------|----------------|-------------|
| `get_pods(namespace)` | Pod phase, container states, restart counts | First call — understand why pods are stuck |
| `describe_deployment(namespace, deploy)` | CPU/mem requests, desired vs ready replicas | Before deciding bump/reduce/scale |
| `get_events(namespace, deploy, last_n)` | Warning + Normal events (OOMKilled, FailedScheduling) | Diagnose root cause |
| `get_pod_logs(namespace, pod_name, tail_lines)` | Last N container log lines | When events don't explain the failure |

#### `agent/llm_agent.py` — LLM Agent

Provider-agnostic. Builds prompts, dispatches to the provider, records per-step metrics. Compatible with the same `Agent` interface as DQN/EpsGreedy.

#### `agent/providers/` — LLM Providers

| Provider | Class | Default model | API key env var |
|----------|-------|--------------|-----------------|
| `gemini` | `GeminiProvider` | `gemini-2.5-flash-lite` | `GEMINI_API_KEY` |
| `anthropic` | `AnthropicProvider` | `claude-sonnet-4-20250514` | `ANTHROPIC_API_KEY` |

#### `benchmark/run.py` — Benchmark Entry Point

| Flag | Default | Description |
|------|---------|-------------|
| `--provider` | `gemini` | `gemini` or `anthropic` |
| `--model` | provider default | Override model string |
| `--ns` | `virtual-default` | Kubernetes namespace |
| `--steps` | 10 | Max steps per episode |
| `--duration` | 60 | Seconds per sim step |
| `--filter-type` | None | Filter by problem_type |
| `--scenario` | None | Run a single named scenario |
| `--list-scenarios` | — | Print scenarios and exit |
| `--max-tool-rounds` | 8 | Max MCP tool calls per step |

---

## The Agent Loop Flow

### Single Step (shared by RL and LLM)

```python
def one_step(trace_path, namespace, deploy, target, duration, agent, reward_name, seed):
    run_hooks("pre_start", namespace)
    sim_uid = create_simulation(name, trace_path, duration, namespace)
    wait_fixed(duration)
    obs = observe(namespace, deploy)          # {"ready": 0, "pending": 3, ...}

    # RL agents:
    action_idx = agent.act(dqn_state_vector)

    # LLM agents:
    action_idx = agent.act(obs, namespace, deploy, step_idx, max_steps)

    out_trace, info = apply_action(trace_path, action_idx, deploy, output_path)
    reward = compute_reward(obs, target, reward_name)
    agent.update(...)                         # no-op for LLM
    write_step_record({...})
    delete_simulation(name, namespace)
    return {"status": 0, "record": {...}}
```

---

## Key Concepts

### Action Space

| Index | Action | Effect |
|-------|--------|--------|
| 0 | `noop` | Do nothing |
| 1 | `bump_cpu_small` | +500m CPU request |
| 2 | `bump_mem_small` | +256Mi memory request |
| 3 | `scale_up_replicas` | +1 replica |
| 4 | `reduce_cpu_small` | −500m CPU request |
| 5 | `reduce_mem_small` | −256Mi memory request |
| 6 | `scale_down_replicas` | −1 replica |

### Traces

MessagePack files containing recorded Kubernetes events. `demo/traces/` contains 100 pre-generated traces. `demo/generate_traces.py` creates more.

### Agents

| Agent | Type | Checkpoint | Best for |
|-------|------|------------|----------|
| `dqn` | Deep Q-Network | `.pt` | Full RL training |
| `greedy` | Epsilon-Greedy | `.json` | Fast prototyping |
| `random` | Random policy | `.json` | Baseline |
| `llm` | LLM + MCP tools | `.json` (metadata) | Benchmark evaluation |
| `bump_cpu` etc. | Hand-coded | none | Debugging |

---

## How to Use

### Setup

```bash
# Install dependencies
pip install -r requirements.txt

# Set up API keys (for LLM benchmarking)
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY and/or ANTHROPIC_API_KEY
```

### Train a DQN Agent

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

---

## LLM Benchmarking

### Quick Start

```bash
# List available scenarios
python benchmark/run.py --list-scenarios

# Run all scenarios with Gemini (default: gemini-2.5-flash-lite)
python benchmark/run.py --provider gemini --ns virtual-default

# Run with a specific model
python benchmark/run.py --provider gemini --model gemini-2.5-flash --ns virtual-default

# Run with Anthropic Claude
python benchmark/run.py --provider anthropic --ns virtual-default

# Single scenario for quick testing
python benchmark/run.py --provider gemini --scenario cpu-insufficient-small --steps 5
```

### Recommended Models

| Model | RPM | RPD | Use case |
|-------|-----|-----|----------|
| `gemini-2.5-flash-lite` | 4K | Unlimited | Default — fast testing, no quota issues |
| `gemini-2.5-flash` | 1K | 10K | Higher reasoning quality |
| `claude-sonnet-4-20250514` | — | — | Anthropic benchmark |

### Benchmark Results

Results are written to `benchmark/results/<timestamp>_<provider>_<model>/`:
- `report.json` — full per-step and per-episode data
- `report.md` — human-readable summary table
- `command.txt` — exact invocation for reproducibility

### Scenario Problem Types

| Type | Description |
|------|-------------|
| `cpu_insufficient` | CPU requests too low; pods stuck Pending |
| `mem_insufficient` | Memory requests too low; pods OOMKilled |
| `replica_deficit` | Fewer replicas than target |
| `combined` | Both resource and replica problems |
| `over_allocation` | Resources far exceed actual usage |

### How the LLM Agent Works

The LLM receives a prompt with the current observation (ready/pending/total pods, target) and has access to four MCP tools it can call in any order before committing to an action. It must respond with a JSON object:

```json
{"action_index": 3, "reasoning": "Only 2 of 5 target replicas are running; scale up."}
```

The response is parsed by `agent/action_parser.py` with three fallback strategies (full JSON → extract JSON block → bare integer) so a malformed response never crashes the loop.

---

## Distributed training (S3 workers and EC2)

For scaling beyond a single machine, jobs are defined as **manifests in S3**; **EC2 workers** poll the bucket, run `runner/train.py`, and upload **checkpoints**, **logs**, and **`result.json`**.

| Topic | Location |
|-------|----------|
| Protocol (manifests, results, CLI) | [`docs/WORKER_PROTOCOL.md`](docs/WORKER_PROTOCOL.md), `protocol/` |
| Launch many EC2 workers + inventory JSON | [`docs/EC2_MULTI_WORKER_RUNBOOK.md`](docs/EC2_MULTI_WORKER_RUNBOOK.md), `ops/ec2_workers.py` |
| Single-instance AMI / S3 secret setup | [`docs/EC2_SETUP_FROM_SCRATCH.md`](docs/EC2_SETUP_FROM_SCRATCH.md) |
| Roadmap (tasks 1–3) | [`docs/NEXT_TASKS.md`](docs/NEXT_TASKS.md) |

**Note:** [`TRAINING_SERVER_README.md`](TRAINING_SERVER_README.md) describes a Flask “central server” that is **not present as `training_server.py` in this repo** — treat it as design unless you add that service. **`runner/dist_run.py`** is currently a **stub**; `job_type=experience_collection` is not end-to-end until that runner is implemented (see [`PROJECT_OUTLINE_CHATGPT.md`](../PROJECT_OUTLINE_CHATGPT.md) §7).

---

## For Future Development

### Adding a New RL Agent

1. Implement your agent class in `agent/`
2. Add a new `AgentType` enum value in `agent/agent.py`
3. Wire up initialization in `runner/train.py`'s argument parsing block

### Adding a New LLM Provider

1. Subclass `LLMProvider` in `agent/providers/`
2. Implement `run_step()` and `model_name`
3. Register in `agent/providers/__init__.py`'s `_PROVIDER_DEFAULTS` dict

### Adding a New MCP Tool

1. Add a function in `sim_mcp/tools/`
2. Register it with `@mcp.tool()` in `sim_mcp/server.py`
3. The tool is automatically available to all LLM providers via `MCPClientSync.anthropic_tools`

### Enhancing Observations (RL)

Add features in `observe/reader.py` and update `state_dim` in `runner/train.py` and the DQN network accordingly.

### Adding Benchmark Scenarios

Add entries to `benchmark/scenarios/index.json` pointing at any trace file in `demo/traces/`.

---

## Quick Reference

### "Where is X happening?"

| What | Where |
|------|-------|
| RL training loop | `runner/train.py` |
| Episode runner | `runner/multi_step.py` |
| Single step (RL + LLM) | `runner/one_step.py` |
| DQN agent | `agent/dqn.py` |
| Epsilon-Greedy agent | `agent/eps_greedy.py` |
| LLM agent | `agent/llm_agent.py` |
| Gemini provider | `agent/providers/gemini_provider.py` |
| Anthropic provider | `agent/providers/anthropic_provider.py` |
| MCP server | `sim_mcp/server.py` |
| MCP client | `sim_mcp/client.py` |
| K8s tools | `sim_mcp/tools/` |
| Benchmark entry point | `benchmark/run.py` |
| Benchmark scenarios | `benchmark/scenarios/index.json` |
| Benchmark metrics | `benchmark/metrics.py` |
| Trace modification | `env/actions/ops.py` |
| Observation extraction | `observe/reader.py` |
| Reward calculation | `observe/reward.py` |
| Simulation management | `env/sim_env.py` |
| Resource safeguards | `runner/safeguards.py` |
| Cluster health checks | `ops/preflight.py` |
| S3 job dispatch (submit/list) | `protocol/dispatch.py` |
| EC2 worker polling loop | `protocol/worker.py` |
| EC2 fleet launch / terminate | `ops/ec2_workers.py` |

### Data Flow

```
                      RL Agent
                     ↗
Trace → Simulation → Cluster → Observation → Agent → Action → Modified Trace
                                                ↘         ↑
                                             LLM Agent     |
                                            (MCP tools) ───┘
                                                  ↓
                                            Reward + Metrics
```
