#!/usr/bin/env python3
"""Generate multiple trace variations with insufficient resources.

Creates 50-100 traces where CPU/memory requests exceed node capacity:
- Node capacity: 16 CPUs, 32GB memory
- Variations: very bad, slightly bad, mixed errors
"""

import json
import random
import sys
from pathlib import Path

# Add project root to Python path
script_dir = Path(__file__).parent.absolute()
project_root = script_dir.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from env.actions.trace_io import json_to_msgpack, save_trace


# Node capacity limits
MAX_CPU = 16  # CPUs
MAX_MEMORY_GB = 32  # GB


def cpu_to_string(cpu: float) -> str:
    """Convert CPU float to Kubernetes format (e.g., 1.5 -> '1500m', 2 -> '2')."""
    if cpu < 1:
        return f"{int(cpu * 1000)}m"
    return str(int(cpu)) if cpu.is_integer() else str(cpu)


def memory_to_string(memory_gb: float) -> str:
    """Convert memory GB to Kubernetes format (e.g., 1 -> '1Gi', 0.5 -> '512Mi')."""
    if memory_gb < 1:
        return f"{int(memory_gb * 1024)}Mi"
    return f"{int(memory_gb)}Gi" if memory_gb.is_integer() else f"{memory_gb}Gi"


def create_trace(cpu_per_pod: float, memory_gb_per_pod: float, replicas: int, trace_id: int) -> dict:
    """Create a trace with specified resource requests."""
    total_cpu = cpu_per_pod * replicas
    total_memory_gb = memory_gb_per_pod * replicas
    
    return {
        "version": 2,
        "config": {},
        "pod_lifecycles": {},
        "index": {},
        "metadata": {
            "description": f"Synthetic trace #{trace_id:04d} - CPU: {total_cpu:.1f}, Memory: {total_memory_gb:.1f}GB, Replicas: {replicas}"
        },
        "events": [
            {
                "ts": 1730390400 + trace_id,
                "applied_objs": [
                    {
                        "apiVersion": "apps/v1",
                        "kind": "Deployment",
                        "metadata": {
                            "name": "web",
                            "namespace": "default"
                        },
                        "spec": {
                            "replicas": replicas,
                            "selector": {
                                "matchLabels": {
                                    "app": "web"
                                }
                            },
                            "template": {
                                "metadata": {
                                    "labels": {
                                        "app": "web"
                                    }
                                },
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "web",
                                            "image": "ghcr.io/example/web:1.0",
                                            "resources": {
                                                "requests": {
                                                    "cpu": cpu_to_string(cpu_per_pod),
                                                    "memory": memory_to_string(memory_gb_per_pod)
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ],
                "deleted_objs": []
            }
        ]
    }


def generate_traces(output_dir: Path, count: int = 75):
    """Generate trace variations with insufficient resources."""
    output_dir.mkdir(parents=True, exist_ok=True)
    
    traces = []
    random.seed(42)  # Reproducible
    
    # Very bad: way over capacity (20-40 CPUs total, 40-80GB memory total)
    for i in range(count // 3):
        replicas = random.choice([2, 3, 4])
        # Ensure total exceeds capacity
        total_cpu_target = random.uniform(20, 40)
        total_memory_target = random.uniform(40, 80)
        cpu_per_pod = total_cpu_target / replicas
        memory_gb_per_pod = total_memory_target / replicas
        traces.append(create_trace(cpu_per_pod, memory_gb_per_pod, replicas, len(traces) + 1))
    
    # Slightly bad: just over capacity (17-20 CPUs total, 33-40GB memory total)
    for i in range(count // 3):
        replicas = random.choice([2, 3])
        total_cpu_target = random.uniform(17, 20)
        total_memory_target = random.uniform(33, 40)
        cpu_per_pod = total_cpu_target / replicas
        memory_gb_per_pod = total_memory_target / replicas
        traces.append(create_trace(cpu_per_pod, memory_gb_per_pod, replicas, len(traces) + 1))
    
    # Mixed errors: CPU over but memory OK, or memory over but CPU OK, or both
    for i in range(count - len(traces)):
        error_type = random.choice(['cpu_only', 'memory_only', 'both'])
        replicas = random.choice([2, 3])
        
        if error_type == 'cpu_only':
            # CPU over (17-24 CPUs total), memory OK (< 32GB total)
            total_cpu_target = random.uniform(17, 24)
            total_memory_target = random.uniform(16, 30)
            cpu_per_pod = total_cpu_target / replicas
            memory_gb_per_pod = total_memory_target / replicas
        elif error_type == 'memory_only':
            # Memory over (33-48GB total), CPU OK (< 16 CPUs total)
            total_cpu_target = random.uniform(8, 15)
            total_memory_target = random.uniform(33, 48)
            cpu_per_pod = total_cpu_target / replicas
            memory_gb_per_pod = total_memory_target / replicas
        else:  # both
            # Both slightly over
            total_cpu_target = random.uniform(17, 20)
            total_memory_target = random.uniform(33, 40)
            cpu_per_pod = total_cpu_target / replicas
            memory_gb_per_pod = total_memory_target / replicas
        
        traces.append(create_trace(cpu_per_pod, memory_gb_per_pod, replicas, len(traces) + 1))
    
    # Save all traces
    for i, trace in enumerate(traces, start=1):
        trace_num = f"{i:04d}"
        json_path = output_dir / f"trace-{trace_num}.json"
        msgpack_path = output_dir / f"trace-{trace_num}.msgpack"
        
        # Save JSON
        with json_path.open("w") as f:
            json.dump(trace, f, indent=2)
        
        # Convert to msgpack
        json_to_msgpack(str(json_path), str(msgpack_path))
    
    print(f"Generated {len(traces)} traces in {output_dir}")
    return len(traces)


if __name__ == "__main__":
    import sys
    
    output_dir = Path("demo/traces")
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 75
    
    generate_traces(output_dir, count)
