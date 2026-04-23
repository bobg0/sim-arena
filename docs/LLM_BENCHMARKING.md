# LLM Benchmarking with MCP

Sim-Arena supports benchmarking large language models (LLMs) on Kubernetes optimization tasks using the Model Context Protocol (MCP) for live cluster observability.

## Overview

LLM agents can query the Kubernetes cluster in real-time using MCP tools to gather information before deciding on actions. This allows evaluation of LLMs' ability to diagnose and fix pod failures.

## Supported Providers

- **Google Gemini**: `gemini-2.5-flash-lite` (default)
- **Anthropic Claude**: `claude-sonnet-4-6`

## Quick Start

```bash
# Set API key
export GEMINI_API_KEY="your_key_here"

# Run benchmark
python benchmark/run.py --provider gemini --ns virtual-default
```

This will:
- Load scenarios from `benchmark/scenarios/`
- Run each scenario with the LLM agent
- Generate reports in `benchmark/results/`

## MCP Tools

LLMs have access to four Kubernetes observability tools:

### get_pods(namespace)
Returns pod phases, container states, and restart counts.

**Example Response:**
```json
[
  {
    "name": "web-12345-abcde",
    "phase": "Pending",
    "containers": [
      {
        "name": "web",
        "state": "Waiting",
        "reason": "Unschedulable"
      }
    ],
    "restart_count": 0
  }
]
```

### describe_deployment(namespace, deployment)
Returns deployment spec including CPU/memory requests and replica counts.

**Example Response:**
```json
{
  "replicas": {
    "desired": 3,
    "ready": 0,
    "available": 0
  },
  "containers": [
    {
      "name": "web",
      "resources": {
        "requests": {
          "cpu": "100m",
          "memory": "128Mi"
        }
      }
    }
  ]
}
```

### get_events(namespace, deployment, last_n=10)
Returns recent events for the deployment.

**Example Response:**
```json
[
  {
    "type": "Warning",
    "reason": "FailedScheduling",
    "message": "0/3 nodes are available: insufficient cpu"
  }
]
```

### get_pod_logs(namespace, pod_name, tail_lines=50)
Returns recent log lines from a pod's container.

**Example Response:**
```json
[
  "Starting web server on port 8080",
  "Error: insufficient memory"
]
```

## Benchmark Scenarios

Scenarios are defined in `benchmark/scenarios/index.json`:

```json
[
  {
    "name": "cpu-overload",
    "trace": "trace-cpu-heavy.msgpack",
    "target": 3,
    "problem_type": "insufficient cpu"
  }
]
```

Each scenario includes:
- Trace file with the failing workload
- Target pod count
- Problem description for context

## LLM Agent Flow

1. **Initial Observation**: Get basic pod counts
2. **Tool Calls**: LLM autonomously calls MCP tools to investigate
3. **Decision**: LLM returns JSON with action index
4. **Action Application**: Same action space as RL agents
5. **Reward Calculation**: Same reward functions

## Metrics Collected

Per-scenario metrics:
- `steps_to_solve`: Steps taken to reach target
- `total_reward`: Cumulative reward
- `tool_calls`: Number of MCP tool invocations
- `latency_ms`: Average response time
- `solved`: Whether target was reached

## Custom Scenarios

1. Generate trace files with `demo/generate_traces.py`
2. Add entry to `benchmark/scenarios/index.json`
3. Run benchmark

## Configuration

### Provider Settings

Modify `agent/providers/` for different models or parameters.

### API Keys

- Gemini: `GEMINI_API_KEY`
- Claude: `ANTHROPIC_API_KEY`

### Cluster Access

Ensure `kubectl` can access the SimKube cluster. The MCP server runs as a subprocess and connects automatically.

## Output

Results are saved to `benchmark/results/<timestamp>/`:
- `report.json`: Detailed metrics
- `report.md`: Human-readable summary
- `step_logs/`: Per-step observations and actions

## Integration

LLM agents use the same `Agent` interface as RL agents:

```python
from agent.agent import Agent, AgentType

agent = Agent(AgentType.LLM, provider="gemini")
action = agent.act(observation)
```