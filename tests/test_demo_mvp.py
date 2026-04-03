<<<<<<< HEAD
from types import SimpleNamespace

from env.actions.trace_io import save_trace
from runner.demo_mvp import _build_cpu_fix_trace, _recovery_succeeded, Snapshot


def test_build_cpu_fix_trace_reduces_existing_trace_cpu(tmp_path):
=======
from env.actions.trace_io import load_trace, save_trace
from runner.demo_mvp import (
    DEFAULT_NAMESPACE,
    PLANNED_ACTIONS,
    _all_expected_pods_ready,
    _apply_action_to_trace,
    _extract_trace_state,
    _final_success,
    Snapshot,
)


def test_planned_actions_are_in_expected_recording_order():
    assert DEFAULT_NAMESPACE == "simkube"
    assert [action["type"] for action in PLANNED_ACTIONS] == [
        "reduce_mem_small",
        "scale_down_replicas",
        "bump_cpu_small",
    ]


def test_planned_actions_transform_composite_trace_to_healthy_target(tmp_path):
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    trace = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
<<<<<<< HEAD
                            "replicas": 3,
=======
                            "replicas": 5,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "resources": {
                                                "requests": {
<<<<<<< HEAD
                                                    "cpu": "17000m",
                                                    "memory": "2Gi",
=======
                                                    "cpu": "250m",
                                                    "memory": "33Gi",
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
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
<<<<<<< HEAD
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
=======
    current_path = tmp_path / "step0.msgpack"
    save_trace(trace, str(current_path))

    for idx, action in enumerate(PLANNED_ACTIONS, start=1):
        next_path = tmp_path / f"step{idx}.msgpack"
        _apply_action_to_trace(str(current_path), "web", action, str(next_path))
        current_path = next_path

    final_state = _extract_trace_state(load_trace(str(current_path)), "web")
    assert final_state == {"cpu": "500m", "memory": "512Mi", "replicas": 3}


def test_final_success_requires_ready_target_and_zero_pending():
    assert _final_success(
        Snapshot(
            obs={"ready": 3, "pending": 0, "total": 3, "assigned": 3, "unschedulable": 0},
            resources={"cpu": "500m", "memory": "512Mi", "replicas": 3},
            pods=[],
        ),
        3,
    ) is True

    assert _final_success(
        Snapshot(
            obs={"ready": 2, "pending": 1, "total": 3, "assigned": 2, "unschedulable": 1},
            resources={"cpu": "500m", "memory": "512Mi", "replicas": 3},
            pods=[],
        ),
        3,
    ) is False


def test_all_expected_pods_ready_requires_running_ready_replicas():
    assert _all_expected_pods_ready(
        Snapshot(
            obs={"ready": 3, "pending": 0, "total": 3, "assigned": 3, "unschedulable": 0},
            resources={"cpu": "500m", "memory": "512Mi", "replicas": 3},
            pods=[],
        ),
    ) is True

    assert _all_expected_pods_ready(
        Snapshot(
            obs={"ready": 2, "pending": 1, "total": 3, "assigned": 3, "unschedulable": 0},
            resources={"cpu": "500m", "memory": "512Mi", "replicas": 3},
            pods=[],
        ),
    ) is False


def test_final_success_rejects_assigned_but_not_ready_pods():
    assert _final_success(
        Snapshot(
            obs={"ready": 0, "pending": 3, "total": 3, "assigned": 3, "unschedulable": 0},
            resources={"cpu": "500m", "memory": "512Mi", "replicas": 3},
            pods=[],
        ),
        3,
    ) is False
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
