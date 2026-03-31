from types import SimpleNamespace

from env.actions.trace_io import save_trace
from runner.demo_mvp import _build_cpu_fix_trace, _recovery_succeeded, Snapshot


def test_build_cpu_fix_trace_reduces_existing_trace_cpu(tmp_path):
    trace = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 3,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "resources": {
                                                "requests": {
                                                    "cpu": "17000m",
                                                    "memory": "2Gi",
                                                }
                                            }
                                        }
                                    ]
                                }
                            },
                        },
                    }
                ]
            }
        ]
    }
    trace_path = tmp_path / "trace.msgpack"
    out_path = tmp_path / "trace-fixed.msgpack"
    save_trace(trace, str(trace_path))

    fixed_path, action = _build_cpu_fix_trace(
        trace_path=str(trace_path),
        deploy="web",
        target_cpu="16000m",
        output_path=str(out_path),
    )

    fixed = SimpleNamespace(path=fixed_path)
    assert fixed.path == str(out_path)
    assert action == {"from_cpu": "17000m", "to_cpu": "16000m", "step": "1000m"}


def test_recovery_succeeded_requires_clear_improvement():
    before = Snapshot(
        obs={"ready": 0, "pending": 3, "total": 3},
        resources={"cpu": "17000m", "memory": "2Gi", "replicas": 3},
        pods=[],
    )
    after = Snapshot(
        obs={"ready": 3, "pending": 0, "total": 3},
        resources={"cpu": "16000m", "memory": "2Gi", "replicas": 3},
        pods=[],
    )

    assert _recovery_succeeded(before, after, target_ready=3) is True


def test_recovery_succeeded_rejects_non_healthy_end_state():
    before = Snapshot(
        obs={"ready": 0, "pending": 3, "total": 3},
        resources={"cpu": "17000m", "memory": "2Gi", "replicas": 3},
        pods=[],
    )
    after = Snapshot(
        obs={"ready": 2, "pending": 1, "total": 3},
        resources={"cpu": "16000m", "memory": "2Gi", "replicas": 3},
        pods=[],
    )

    assert _recovery_succeeded(before, after, target_ready=3) is False
