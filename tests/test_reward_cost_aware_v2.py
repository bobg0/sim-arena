#!/usr/bin/env python3
"""
Tuning and sanity checks for reward_cost_aware_v2.

Run: PYTHONPATH=. pytest tests/test_reward_cost_aware_v2.py -v -s

Or: PYTHONPATH=. python tests/test_reward_cost_aware_v2.py

Sanity properties:
1. Healthy but wasteful config → reward should drop visibly (e.g. 0.9 → 0.5–0.7)
2. Unhealthy config → best actions should increase reward monotonically as readiness improves

Tuning tips:
- If cost isn't "felt" enough after health: increase 0.6 → 0.8 in healthy branch
- If agent becomes too stingy and fails to fix health: decrease 0.15 → 0.05 in unhealthy branch
"""

import sys
from pathlib import Path

project_root = Path(__file__).parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from observe.reward import reward_cost_aware


# Representative configs: (obs, resources, target_total, trace_type, description)
# Format: obs = {ready, pending, total}, resources = {cpu, memory, replicas}
TARGET = 3

# --- reduce_cpu type (2-3 traces: slight, heavy, cpu+mem) ---
REDUCE_CPU_CONFIGS = [
    # Initial: all pending, CPU way over
    (
        {"ready": 0, "pending": 3, "total": 3},
        {"cpu": "17000m", "memory": "2Gi", "replicas": 3},
        TARGET,
        "reduce_cpu",
        "Initial (trace-cpu-slight): 0 ready, 3 pending, 17 CPU/pod",
    ),
    # Mid: partial progress
    (
        {"ready": 1, "pending": 2, "total": 3},
        {"cpu": "12000m", "memory": "2Gi", "replicas": 3},
        TARGET,
        "reduce_cpu",
        "Mid: 1 ready, 2 pending, 12 CPU/pod",
    ),
    # Healthy, efficient
    (
        {"ready": 3, "pending": 0, "total": 3},
        {"cpu": "500m", "memory": "256Mi", "replicas": 3},
        TARGET,
        "reduce_cpu",
        "Healthy efficient: 3 ready, 500m/256Mi",
    ),
    # Healthy, wasteful (high CPU)
    (
        {"ready": 3, "pending": 0, "total": 3},
        {"cpu": "10000m", "memory": "2Gi", "replicas": 3},
        TARGET,
        "reduce_cpu",
        "Healthy wasteful: 3 ready, 10 CPU/pod",
    ),
]

# --- reduce_mem type ---
REDUCE_MEM_CONFIGS = [
    (
        {"ready": 0, "pending": 3, "total": 3},
        {"cpu": "500m", "memory": "33Gi", "replicas": 3},
        TARGET,
        "reduce_mem",
        "Initial (trace-mem-slight): 0 ready, 3 pending, 33Gi/pod (exceeds 32Gi/node)",
    ),
    (
        {"ready": 2, "pending": 1, "total": 3},
        {"cpu": "500m", "memory": "8Gi", "replicas": 3},
        TARGET,
        "reduce_mem",
        "Mid: 2 ready, 1 pending, 8Gi/pod",
    ),
    (
        {"ready": 3, "pending": 0, "total": 3},
        {"cpu": "500m", "memory": "256Mi", "replicas": 3},
        TARGET,
        "reduce_mem",
        "Healthy efficient: 3 ready, 256Mi/pod",
    ),
    (
        {"ready": 3, "pending": 0, "total": 3},
        {"cpu": "500m", "memory": "8Gi", "replicas": 3},
        TARGET,
        "reduce_mem",
        "Healthy wasteful: 3 ready, 8Gi/pod",
    ),
]

# --- replicas_over type ---
REPLICAS_OVER_CONFIGS = [
    (
        {"ready": 5, "pending": 0, "total": 5},
        {"cpu": "500m", "memory": "512Mi", "replicas": 5},
        TARGET,
        "replicas_over",
        "Healthy but wasteful: 5 replicas when target is 3",
    ),
    (
        {"ready": 3, "pending": 0, "total": 5},
        {"cpu": "500m", "memory": "512Mi", "replicas": 5},
        TARGET,
        "replicas_over",
        "3 ready, 5 total (overshoot)",
    ),
    (
        {"ready": 3, "pending": 0, "total": 3},
        {"cpu": "500m", "memory": "512Mi", "replicas": 3},
        TARGET,
        "replicas_over",
        "Healthy efficient: exact target",
    ),
]


def _format_row(c: dict, step_label: str = "") -> str:
    return (
        f"  {step_label:30} | "
        f"ready={c['ready']} pending={c['pending']} total={c['total']} | "
        f"cpu={c['cpu_per_pod_m']}m mem={c['mem_per_pod_b']//(1024**2)}Mi | "
        f"health={c['health']:+.2f} cost={c['cost']:.2f} reward={c['reward']:.3f}"
    )


def run_tuning_report():
    """Print detailed report for all representative configs."""
    print("=" * 90)
    print("reward_cost_aware_v2 — Tuning Report")
    print("=" * 90)

    all_configs = [
        *REDUCE_CPU_CONFIGS,
        *REDUCE_MEM_CONFIGS,
        *REPLICAS_OVER_CONFIGS,
    ]

    for obs, resources, target, trace_type, desc in all_configs:
        c = reward_cost_aware(obs, target, resources)
        c["mem_per_pod_b"] = c["mem_per_pod_b"]  # already in return
        print(f"\n[{trace_type}] {desc}")
        print(_format_row(c))

    print("\n" + "=" * 90)
    print("Sanity Checks")
    print("=" * 90)


def test_healthy_wasteful_drops_reward():
    """
    Sanity 1: Healthy but wasteful → reward should drop visibly (0.9 → 0.5–0.7).
    """
    # Efficient: 3 ready, 500m/256Mi
    c_eff = reward_cost_aware(
        {"ready": 3, "pending": 0, "total": 3},
        TARGET,
        {"cpu": "500m", "memory": "256Mi", "replicas": 3},
    )
    # Wasteful CPU: 3 ready, 10 CPU/pod
    c_waste_cpu = reward_cost_aware(
        {"ready": 3, "pending": 0, "total": 3},
        TARGET,
        {"cpu": "10000m", "memory": "2Gi", "replicas": 3},
    )
    # Wasteful replicas: 5 ready, 5 total
    c_waste_rep = reward_cost_aware(
        {"ready": 5, "pending": 0, "total": 5},
        TARGET,
        {"cpu": "500m", "memory": "512Mi", "replicas": 5},
    )

    assert c_eff["healthy"] and c_waste_cpu["healthy"] and c_waste_rep["healthy"]
    assert c_eff["reward"] > c_waste_cpu["reward"], (
        f"Efficient (r={c_eff['reward']:.3f}) should score higher than wasteful CPU (r={c_waste_cpu['reward']:.3f})"
    )
    assert c_eff["reward"] > c_waste_rep["reward"], (
        f"Efficient (r={c_eff['reward']:.3f}) should score higher than wasteful replicas (r={c_waste_rep['reward']:.3f})"
    )
    assert 0.5 <= c_waste_cpu["reward"] <= 0.9, (
        f"Healthy wasteful CPU reward {c_waste_cpu['reward']:.3f} should be in [0.5, 0.9]"
    )
    assert 0.5 <= c_waste_rep["reward"] <= 0.9, (
        f"Healthy wasteful replicas reward {c_waste_rep['reward']:.3f} should be in [0.5, 0.9]"
    )


def test_unhealthy_monotonicity():
    """
    Sanity 2: As readiness improves (0→1→2→3 ready), reward should increase.
    Simulate a reduce_cpu path: same resources, improving obs.
    """
    resources = {"cpu": "5000m", "memory": "2Gi", "replicas": 3}
    rewards = []
    for ready in range(4):
        pending = 3 - ready
        obs = {"ready": ready, "pending": pending, "total": 3}
        c = reward_cost_aware(obs, TARGET, resources)
        rewards.append(c["reward"])

    for i in range(1, len(rewards)):
        assert rewards[i] >= rewards[i - 1] - 0.01, (
            f"Reward should increase as ready goes 0→1→2→3: {rewards}"
        )


def test_reduce_cpu_progression():
    """Log a simulated reduce_cpu episode path."""
    print("\n--- Simulated reduce_cpu progression (17000m → 500m) ---")
    steps = [
        ({"ready": 0, "pending": 3, "total": 3}, {"cpu": "17000m", "memory": "2Gi", "replicas": 3}),
        ({"ready": 0, "pending": 3, "total": 3}, {"cpu": "12000m", "memory": "2Gi", "replicas": 3}),
        ({"ready": 1, "pending": 2, "total": 3}, {"cpu": "8000m", "memory": "2Gi", "replicas": 3}),
        ({"ready": 2, "pending": 1, "total": 3}, {"cpu": "5000m", "memory": "2Gi", "replicas": 3}),
        ({"ready": 3, "pending": 0, "total": 3}, {"cpu": "5000m", "memory": "2Gi", "replicas": 3}),
        ({"ready": 3, "pending": 0, "total": 3}, {"cpu": "500m", "memory": "256Mi", "replicas": 3}),
    ]
    for i, (obs, res) in enumerate(steps):
        c = reward_cost_aware(obs, TARGET, res)
        print(_format_row(c, f"Step {i}"))


def test_reduce_mem_progression():
    """Log a simulated reduce_mem episode path."""
    print("\n--- Simulated reduce_mem progression (33Gi → 256Mi) ---")
    steps = [
        ({"ready": 0, "pending": 3, "total": 3}, {"cpu": "500m", "memory": "33Gi", "replicas": 3}),
        ({"ready": 0, "pending": 3, "total": 3}, {"cpu": "500m", "memory": "8Gi", "replicas": 3}),
        ({"ready": 2, "pending": 1, "total": 3}, {"cpu": "500m", "memory": "4Gi", "replicas": 3}),
        ({"ready": 3, "pending": 0, "total": 3}, {"cpu": "500m", "memory": "1Gi", "replicas": 3}),
        ({"ready": 3, "pending": 0, "total": 3}, {"cpu": "500m", "memory": "256Mi", "replicas": 3}),
    ]
    for i, (obs, res) in enumerate(steps):
        c = reward_cost_aware(obs, TARGET, res)
        print(_format_row(c, f"Step {i}"))


def test_replicas_over_progression():
    """Log a simulated replicas_over episode path."""
    print("\n--- Simulated replicas_over progression (5 → 3) ---")
    steps = [
        ({"ready": 5, "pending": 0, "total": 5}, {"cpu": "500m", "memory": "512Mi", "replicas": 5}),
        ({"ready": 4, "pending": 0, "total": 4}, {"cpu": "500m", "memory": "512Mi", "replicas": 4}),
        ({"ready": 3, "pending": 0, "total": 3}, {"cpu": "500m", "memory": "512Mi", "replicas": 3}),
    ]
    for i, (obs, res) in enumerate(steps):
        c = reward_cost_aware(obs, TARGET, res)
        print(_format_row(c, f"Step {i}"))


if __name__ == "__main__":
    run_tuning_report()
    test_reduce_cpu_progression()
    test_reduce_mem_progression()
    test_replicas_over_progression()
    test_healthy_wasteful_drops_reward()
    test_unhealthy_monotonicity()
    print("\n✓ All sanity checks passed.")
