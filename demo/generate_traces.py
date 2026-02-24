#!/usr/bin/env python3
"""Generate named test traces for the sim-arena training environment.

SimKube schedules pods on KWOK virtual nodes (type=virtual), each with 16 CPU, 32Gi.
Six scenario types for diverse training (agent randomly gets one per episode):

  trace-cpu-slight   -- CPU over: 3 x 17000m (reduce_cpu)
  trace-cpu-heavy    -- CPU far over: 3 x 20000m (reduce_cpu)
  trace-mem-slight   -- Memory over: 3 x 12Gi (reduce_mem)
  trace-mem-heavy    -- Memory far over: 3 x 15Gi (reduce_mem)
  trace-cpu-mem      -- Both over: 3 x 17000m + 12Gi (reduce both)
  trace-replicas-over -- Too many replicas: 5 x 500m (scale_down to 3)

Usage:
  PYTHONPATH=. python demo/generate_traces.py
"""

import json
import sys
from pathlib import Path

# Add project root to Python path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from env.actions.trace_io import json_to_msgpack


def _make_trace(
    cpu_per_pod: str,
    memory_per_pod: str,
    replicas: int,
    description: str,
    scenario: dict,
) -> dict:
    """Build a trace dict in SimKube v2 format."""
    return {
        "version": 2,
        "config": {
            "trackedObjects": {
                "apps/v1.Deployment": {
                    "podSpecTemplatePath": "/spec/template"
                }
            }
        },
        "pod_lifecycles": {},
        "index": {},
        "metadata": {
            "description": description,
            "scenario": scenario,
        },
        "events": [
            {
                "ts": 1730390400,
                "deleted_objs": [],
                "applied_objs": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {"name": "web", "namespace": "default"},
                        "spec": {
                            "selector": {"matchLabels": {"app": "web"}},
                            "replicas": replicas,
                            "template": {
                                "metadata": {"labels": {"app": "web"}},
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "web",
                                            "image": "ghcr.io/example/web:1.0",
                                            "resources": {
                                                "requests": {
                                                    "cpu": cpu_per_pod,
                                                    "memory": memory_per_pod,
                                                }
                                            },
                                        }
                                    ]
                                },
                            },
                        },
                    }
                ],
            }
        ],
    }


# ---- Trace definitions ----

TRACES = {
    "trace-cpu-slight": _make_trace(
        cpu_per_pod="17000m",
        memory_per_pod="2Gi",
        replicas=3,
        description="CPU slight: 3 replicas x 17000m = 51 CPUs (exceeds 16 CPU KWOK node -> 1+ pending)",
        scenario={
            "failure_mode": "cpu_only",
            "severity": "slight",
            "initial_state": "3 pods, 17000m CPU each (51 CPUs total), exceeds 16 CPU/node",
            "target": "3 pods ready",
            "expected_behavior": "Agent should reduce CPU multiple times to get under 16 CPU/node limit",
        },
    ),
    "trace-cpu-heavy": _make_trace(
        cpu_per_pod="20000m",
        memory_per_pod="2Gi",
        replicas=3,
        description="CPU heavy: 3 replicas x 20000m = 60 CPUs (far over 16 CPU KWOK node limit)",
        scenario={
            "failure_mode": "cpu_only",
            "severity": "heavy",
            "initial_state": "3 pods, 20000m CPU each (60 CPUs total), far over node capacity",
            "target": "3 pods ready",
            "expected_behavior": "Agent should reduce CPU multiple times to get under 16 CPU/node limit",
        },
    ),
    "trace-mem-slight": _make_trace(
        cpu_per_pod="500m",
        memory_per_pod="12Gi",
        replicas=3,
        description="Memory slight: 3 x 12Gi = 36Gi (exceeds 32Gi KWOK node)",
        scenario={
            "failure_mode": "memory_only",
            "severity": "slight",
            "initial_state": "3 pods, 12Gi each (36Gi total), exceeds 32Gi/node",
            "target": "3 pods ready",
            "expected_behavior": "Agent should reduce memory to get under 32Gi/node limit",
        },
    ),
    "trace-mem-heavy": _make_trace(
        cpu_per_pod="500m",
        memory_per_pod="15Gi",
        replicas=3,
        description="Memory heavy: 3 x 15Gi = 45Gi (far over 32Gi limit)",
        scenario={
            "failure_mode": "memory_only",
            "severity": "heavy",
            "initial_state": "3 pods, 15Gi each (45Gi total), far over node capacity",
            "target": "3 pods ready",
            "expected_behavior": "Agent should reduce memory multiple times",
        },
    ),
    "trace-cpu-mem": _make_trace(
        cpu_per_pod="17000m",
        memory_per_pod="12Gi",
        replicas=3,
        description="Both over: 3 x 17 CPU + 12Gi (exceeds 16 CPU and 32Gi per node)",
        scenario={
            "failure_mode": "cpu_and_memory",
            "severity": "medium",
            "initial_state": "3 pods, 17 CPU + 12Gi each - both over node limits",
            "target": "3 pods ready",
            "expected_behavior": "Agent should reduce both CPU and memory",
        },
    ),
    "trace-replicas-over": _make_trace(
        cpu_per_pod="500m",
        memory_per_pod="512Mi",
        replicas=5,
        description="Replicas over: 5 replicas when target is 3 (scale_down)",
        scenario={
            "failure_mode": "replicas_only",
            "severity": "slight",
            "initial_state": "5 pods (all schedule), target is 3",
            "target": "3 pods ready",
            "expected_behavior": "Agent should scale_down_replicas to 3",
        },
    ),
}


def generate_traces(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    for name, trace in TRACES.items():
        json_path = output_dir / f"{name}.json"
        msgpack_path = output_dir / f"{name}.msgpack"

        with json_path.open("w") as f:
            json.dump(trace, f, indent=2)

        json_to_msgpack(str(json_path), str(msgpack_path))
        print(f"  {name}.json + {name}.msgpack")

    print(f"\nGenerated {len(TRACES)} traces in {output_dir}/")


if __name__ == "__main__":
    output_dir = Path(__file__).parent
    generate_traces(output_dir)
