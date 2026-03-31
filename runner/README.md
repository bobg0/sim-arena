Reproducing One Step

pre_start hook
→ create_simulation
→ wait_fixed(120)
→ observe
→ simple policy
→ apply action (edit trace)
→ write .tmp/trace-next.msgpack
→ compute reward
→ write logs (runs/step.jsonl & runs/summary.json)



Run a single step
From the repo root:

make preflight

sk-run one-step \
    --trace demo/trace-0001.msgpack \
    --ns test-ns \
    --deploy web \
    --target 3

Expected Output After running:
runs/step.jsonl will contain one line with:
obs (cluster state)
action (e.g., bump_cpu_small or noop)
reward
trace paths
runs/summary.json will be updated with totals.
.tmp/trace-next.msgpack will be created and can be used for the next step.

MVP Demo

From the repo root, after activating the repo venv:

python -m runner.demo_mvp

Defaults:
- Uses `demo/trace-cpu-slight.msgpack`
- Observes `deployment/web` in `virtual-default`
- Replays the failing trace, applies one CPU remediation with the existing `reduce_cpu_small` op, then replays the fixed trace

Requirements:
- Current kube context must point at the SimKube cluster
- SimKube must be running and able to read traces from the mounted `/data` path

Success looks like:
- `Before` shows Pending pods and fewer than the target Ready pods
- `After` shows `3 ready | 0 pending`
- Final line prints `verdict         SUCCESS`

## 🚀 Quickstart: Gymnasium Environment

We've wrapped our SimKube simulation loop into a standard [Gymnasium](https://gymnasium.farama.org/) environment. This makes it plug-and-play with standard reinforcement learning libraries like Stable Baselines3 or Ray RLlib.
