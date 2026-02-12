"""Tests for runner/multi_step.py"""

from unittest.mock import patch

from runner.multi_step import run_episode


def test_run_episode_calls_one_step(tmp_path):
    """Test run_episode calls one_step for each step and returns summary."""
    from env.actions.trace_io import save_trace
    trace_path = tmp_path / "trace.msgpack"
    save_trace(
        {"events": [{"applied_objs": [{"kind": "Deployment", "metadata": {"name": "web"}, "spec": {"replicas": 2}}]}]},
        str(trace_path),
    )
    out_trace = tmp_path / ".tmp" / "trace-next.msgpack"
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    save_trace({"events": [{"applied_objs": []}]}, str(out_trace))

    with patch("runner.multi_step.one_step") as mock_one_step:
        mock_one_step.return_value = {
            "status": 0,
            "record": {
                "trace_out": str(out_trace),
                "reward": 1,
                "obs": {"ready": 3, "pending": 0, "total": 3},
            },
        }
        result = run_episode(
            trace_path=str(trace_path),
            namespace="test-ns",
            deploy="web",
            target=3,
            duration=10,
            steps=2,
            seed=42,
            agent_name="heuristic",
            reward_name="base",
            agent=None,
        )
        assert result["status"] == 0
        assert result["steps_executed"] == 2
        assert result["total_reward"] == 2
        assert len(result["records"]) == 2
        assert mock_one_step.call_count == 2


def test_run_episode_calls_one_step_with_policy(tmp_path):
    """Test run_episode with policy (heuristic) passes agent=None."""
    from env.actions.trace_io import save_trace
    trace_path = tmp_path / "trace.msgpack"
    save_trace({"events": [{"applied_objs": []}]}, str(trace_path))
    out_trace = tmp_path / ".tmp" / "trace-next.msgpack"
    out_trace.parent.mkdir(parents=True, exist_ok=True)
    save_trace({"events": []}, str(out_trace))

    with patch("runner.multi_step.one_step") as mock_one_step:
        mock_one_step.return_value = {"status": 0, "record": {"trace_out": str(out_trace), "reward": 0}}
        run_episode(
            trace_path=str(trace_path),
            namespace="test-ns",
            deploy="web",
            target=3,
            duration=5,
            steps=1,
            agent_name="heuristic",
            agent=None,
        )
        call_kwargs = mock_one_step.call_args[1]
        assert call_kwargs["agent_name"] == "heuristic"
        assert call_kwargs["agent"] is None
        assert call_kwargs["reward_name"] == "shaped"  # default for multi-step


def test_run_episode_stops_on_failure(tmp_path):
    """Test run_episode stops when one_step returns non-zero status."""
    from env.actions.trace_io import save_trace
    trace_path = tmp_path / "trace.msgpack"
    save_trace({"events": [{"applied_objs": []}]}, str(trace_path))

    with patch("runner.multi_step.one_step") as mock_one_step:
        mock_one_step.return_value = {"status": 1, "record": None}
        result = run_episode(
            trace_path=str(trace_path),
            namespace="test-ns",
            deploy="web",
            target=3,
            duration=5,
            steps=3,
            agent_name="heuristic",
            agent=None,
        )
        assert result["steps_executed"] == 0
        assert mock_one_step.call_count == 1
