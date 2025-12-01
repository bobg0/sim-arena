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