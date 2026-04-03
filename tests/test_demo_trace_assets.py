import json
from pathlib import Path


def test_composite_demo_trace_matches_intended_mixture():
    trace_path = Path("demo/trace-cpu-low-mem-high-replicas-over.json")
    trace = json.loads(trace_path.read_text())

    deployment = trace["events"][0]["applied_objs"][0]
    requests = deployment["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]
    scenario = trace["metadata"]["scenario"]

    assert deployment["spec"]["replicas"] == 5
    assert requests["cpu"] == "250m"
    assert requests["memory"] == "33Gi"
    assert scenario["failure_mode"] == "cpu_low_memory_high_replicas_over"
    assert scenario["expected_behavior"] == "Agent should bump CPU, reduce memory, and scale_down_replicas to 3"
