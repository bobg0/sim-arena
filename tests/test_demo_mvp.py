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
    trace = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 5,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "resources": {
                                                "requests": {
                                                    "cpu": "250m",
                                                    "memory": "33Gi",
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
