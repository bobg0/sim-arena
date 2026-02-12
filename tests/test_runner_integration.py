"""
Integration tests for runner/one_step.py

These tests mock all Kubernetes dependencies so they can run without a cluster.
"""

import json
import shutil
from unittest.mock import patch

import pytest

# Import the functions we're testing
from runner.one_step import (
    one_step,
    apply_action,
    _extract_current_state,
    deterministic_id,
    write_step_record,
    update_summary,
)
from runner.policies import get_policy


@pytest.fixture
def temp_workspace(tmp_path):
    """Create a temporary workspace with demo trace and runs directory."""
    # Create demo trace
    demo_dir = tmp_path / "demo"
    demo_dir.mkdir()
    
    trace_data = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 2,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {
                                            "name": "web",
                                            "resources": {
                                                "requests": {
                                                    "cpu": "100m",
                                                    "memory": "128Mi"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }
    
    # Save as msgpack
    from env.actions.trace_io import save_trace
    trace_path = demo_dir / "trace-test.msgpack"
    save_trace(trace_data, str(trace_path))
    
    # Create runs directory
    runs_dir = tmp_path / "runs"
    runs_dir.mkdir()
    
    # Create .tmp directory
    tmp_dir = tmp_path / ".tmp"
    tmp_dir.mkdir()
    
    return {
        "root": tmp_path,
        "trace_path": str(trace_path),
        "runs_dir": runs_dir,
        "tmp_dir": tmp_dir,
    }


@pytest.fixture
def mock_k8s_deps():
    """Mock all Kubernetes dependencies."""
    with patch('runner.one_step.run_hooks') as mock_hooks, \
         patch('runner.one_step.create_simulation') as mock_create, \
         patch('runner.one_step.wait_fixed') as mock_wait, \
         patch('runner.one_step.observe') as mock_observe, \
         patch('runner.one_step.current_requests') as mock_current_requests, \
         patch('runner.one_step.delete_simulation') as mock_delete, \
         patch('runner.one_step.shutil.copy2') as mock_copy:
        
        # Configure mock returns
        mock_create.return_value = "sim-test-12345678"
        mock_observe.return_value = {"ready": 2, "pending": 1, "total": 3}
        mock_current_requests.return_value = {"cpu": "100m", "memory": "128Mi", "replicas": 2}
        
        yield {
            "hooks": mock_hooks,
            "create": mock_create,
            "wait": mock_wait,
            "observe": mock_observe,
            "current_requests": mock_current_requests,
            "delete": mock_delete,
            "copy": mock_copy,
        }


# ===== Unit Tests for Helper Functions =====

def test_deterministic_id():
    """Test that deterministic_id produces consistent, short IDs."""
    id1 = deterministic_id(
        trace_path="demo/trace.msgpack",
        namespace="test-ns",
        deploy="web",
        target=3,
        timestamp="2025-11-12T10:00:00Z"
    )
    
    # Should be 8 characters (MD5 hash truncated)
    assert len(id1) == 8
    assert isinstance(id1, str)
    
    # Should be deterministic
    id2 = deterministic_id(
        trace_path="demo/trace.msgpack",
        namespace="test-ns",
        deploy="web",
        target=3,
        timestamp="2025-11-12T10:00:00Z"
    )
    assert id1 == id2
    
    # Different inputs should produce different IDs
    id3 = deterministic_id(
        trace_path="demo/trace.msgpack",
        namespace="test-ns",
        deploy="web",
        target=4,  # Different target
        timestamp="2025-11-12T10:00:00Z"
    )
    assert id1 != id3


def test_write_step_record(tmp_path):
    """Test that write_step_record appends to JSONL file."""
    step_log = tmp_path / "step.jsonl"
    
    # Patch the STEP_LOG constant
    with patch('runner.one_step.STEP_LOG', step_log):
        record1 = {"step": 1, "reward": 0}
        record2 = {"step": 2, "reward": 1}
        
        write_step_record(record1)
        write_step_record(record2)
        
        # Read and verify
        lines = step_log.read_text().strip().split('\n')
        assert len(lines) == 2
        assert json.loads(lines[0]) == record1
        assert json.loads(lines[1]) == record2


def test_update_summary_new_file(tmp_path):
    """Test that update_summary creates a new summary file."""
    summary_log = tmp_path / "summary.json"
    
    with patch('runner.one_step.SUMMARY_LOG', summary_log):
        record = {"step": 1, "reward": 1}
        update_summary(record)
        
        # Read and verify
        summary = json.loads(summary_log.read_text())
        assert summary["total_steps"] == 1
        assert summary["total_rewards"] == 1
        assert len(summary["steps"]) == 1
        assert summary["steps"][0] == record


def test_update_summary_append(tmp_path):
    """Test that update_summary appends to existing summary."""
    summary_log = tmp_path / "summary.json"
    
    # Create initial summary
    initial = {
        "steps": [{"step": 1, "reward": 0}],
        "total_steps": 1,
        "total_rewards": 0
    }
    summary_log.write_text(json.dumps(initial))
    
    with patch('runner.one_step.SUMMARY_LOG', summary_log):
        record = {"step": 2, "reward": 1}
        update_summary(record)
        
        # Read and verify
        summary = json.loads(summary_log.read_text())
        assert summary["total_steps"] == 2
        assert summary["total_rewards"] == 1
        assert len(summary["steps"]) == 2


def test_heuristic_policy_with_pending():
    """Test that heuristic policy chooses bump_cpu_small when pods are pending."""
    policy = get_policy("heuristic")
    obs = {"ready": 2, "pending": 1, "total": 3}
    action = policy(obs=obs, deploy="web")
    
    assert action["type"] == "bump_cpu_small"
    assert action["deploy"] == "web"


def test_heuristic_policy_noop():
    """Test that heuristic policy chooses noop when no pods are pending."""
    policy = get_policy("heuristic")
    obs = {"ready": 3, "pending": 0, "total": 3}
    action = policy(obs=obs, deploy="web")
    
    assert action["type"] == "noop"


def test_extract_current_state():
    """Test _extract_current_state extracts CPU, memory, replicas from trace."""
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
                                                    "cpu": "500m",
                                                    "memory": "256Mi"
                                                }
                                            }
                                        }
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }
    state = _extract_current_state(trace, "web")
    assert state["cpu"] == "500m"
    assert state["memory"] == "256Mi"
    assert state["replicas"] == 3


def test_extract_current_state_deployment_not_found():
    """Test _extract_current_state returns defaults when deployment not found."""
    trace = {"events": [{"applied_objs": []}]}
    state = _extract_current_state(trace, "nonexistent")
    assert state["cpu"] == "0m"
    assert state["memory"] == "0Mi"
    assert state["replicas"] == 0


def test_apply_action_noop(tmp_path):
    """Test apply_action with noop saves trace unchanged."""
    from env.actions.trace_io import load_trace, save_trace
    trace_path = tmp_path / "trace.msgpack"
    out_path = tmp_path / "out.msgpack"
    trace_data = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 2,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }
    save_trace(trace_data, str(trace_path))
    out_path_arg, info = apply_action(str(trace_path), {"type": "noop"}, "web", str(out_path))
    assert info["action_type"] == "noop"
    assert info["blocked"] is False
    assert info["changed"] is False
    loaded = load_trace(str(out_path))
    assert loaded["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] == "100m"


def test_apply_action_bump_cpu(tmp_path):
    """Test apply_action with bump_cpu_small modifies trace."""
    from env.actions.trace_io import load_trace, save_trace
    trace_path = tmp_path / "trace.msgpack"
    out_path = tmp_path / "out.msgpack"
    trace_data = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 2,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"resources": {"requests": {"cpu": "100m", "memory": "128Mi"}}}
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }
    save_trace(trace_data, str(trace_path))
    out_path_arg, info = apply_action(str(trace_path), {"type": "bump_cpu_small", "step": "500m"}, "web", str(out_path))
    assert info["changed"] is True
    assert info["blocked"] is False
    loaded = load_trace(str(out_path))
    assert loaded["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] == "600m"


def test_apply_action_blocked_by_safeguards(tmp_path):
    """Test apply_action with bump_cpu_small is blocked when CPU exceeds limit."""
    from env.actions.trace_io import load_trace, save_trace
    # CPU at 16000m (16 CPUs) = at limit; bumping 500m would exceed
    trace_path = tmp_path / "trace.msgpack"
    out_path = tmp_path / "out.msgpack"
    trace_data = {
        "events": [
            {
                "applied_objs": [
                    {
                        "kind": "Deployment",
                        "metadata": {"name": "web"},
                        "spec": {
                            "replicas": 2,
                            "template": {
                                "spec": {
                                    "containers": [
                                        {"resources": {"requests": {"cpu": "16000m", "memory": "512Mi"}}}
                                    ]
                                }
                            }
                        }
                    }
                ]
            }
        ]
    }
    save_trace(trace_data, str(trace_path))
    out_path_arg, info = apply_action(str(trace_path), {"type": "bump_cpu_small", "step": "500m"}, "web", str(out_path))
    assert info["blocked"] is True
    assert info["changed"] is False
    assert "error" in info
    # Trace should be saved unchanged
    loaded = load_trace(str(out_path))
    assert loaded["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]["resources"]["requests"]["cpu"] == "16000m"


# ===== Integration Tests for one_step() =====

def test_one_step_happy_path_with_action(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test complete one_step flow when policy takes action."""
    # Change working directory to temp workspace
    monkeypatch.chdir(temp_workspace["root"])
    
    # Configure mocks
    mock_k8s_deps["observe"].return_value = {"ready": 2, "pending": 1, "total": 3}
    
    # Run one_step
    result = one_step(
        trace_path=temp_workspace["trace_path"],
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=10,
        seed=42
    )
    
    # Verify return value (one_step returns dict with status)
    assert result["status"] == 0
    
    # Verify all K8s functions were called in order
    # one_step uses virtual-default for observe/hooks (SimKube creates pods there)
    mock_k8s_deps["hooks"].assert_called_once_with("pre_start", "virtual-default", deploy="web")
    
    # Check create_simulation was called with correct args
    create_call = mock_k8s_deps["create"].call_args
    assert create_call[1]["namespace"] == "test-ns"
    assert create_call[1]["duration_s"] == 10
    assert "diag-" in create_call[1]["name"]
    
    mock_k8s_deps["wait"].assert_called_once_with(10)
    mock_k8s_deps["observe"].assert_called_once_with("virtual-default", "web")
    
    # Check delete_simulation was called (cleanup)
    mock_k8s_deps["delete"].assert_called_once()
    delete_call = mock_k8s_deps["delete"].call_args
    assert delete_call[0][1] == "test-ns"  # namespace
    
    # Verify trace was modified and saved
    tmp_trace = temp_workspace["root"] / ".tmp" / "trace-next.msgpack"
    assert tmp_trace.exists()
    
    from env.actions.trace_io import load_trace
    modified_trace = load_trace(str(tmp_trace))
    
    # CPU should have been bumped by 500m (100m -> 600m) by heuristic policy
    container = modified_trace["events"][0]["applied_objs"][0]["spec"]["template"]["spec"]["containers"][0]
    assert container["resources"]["requests"]["cpu"] == "600m"
    
    # Verify logs were written
    step_log = temp_workspace["root"] / "runs" / "step.jsonl"
    assert step_log.exists()
    
    summary_log = temp_workspace["root"] / "runs" / "summary.json"
    assert summary_log.exists()
    
    # Verify step record
    step_records = [json.loads(line) for line in step_log.read_text().strip().split('\n')]
    assert len(step_records) == 1
    record = step_records[0]
    assert record["namespace"] == "virtual-default"
    assert record["obs"] == {"ready": 2, "pending": 1, "total": 3}
    assert record["action"]["type"] == "bump_cpu_small"
    # reward_shaped: distance=1 (-0.1), pending=1 (-0.05) -> -0.15
    assert record["reward"] == pytest.approx(-0.15)


def test_one_step_noop_action(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test one_step when policy chooses noop (no pending pods)."""
    monkeypatch.chdir(temp_workspace["root"])
    
    # All pods ready - should trigger noop
    mock_k8s_deps["observe"].return_value = {"ready": 3, "pending": 0, "total": 3}
    
    result = one_step(
        trace_path=temp_workspace["trace_path"],
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=10,
        seed=42
    )
    
    assert result["status"] == 0
    
    # Verify trace was still saved (copy)
    tmp_trace = temp_workspace["root"] / ".tmp" / "trace-next.msgpack"
    assert tmp_trace.exists()
    
    # Verify step record shows noop
    step_log = temp_workspace["root"] / "runs" / "step.jsonl"
    step_records = [json.loads(line) for line in step_log.read_text().strip().split('\n')]
    assert step_records[0]["action"]["type"] == "noop"
    assert step_records[0]["reward"] == 1.0  # reward_shaped: perfect match -> 1.0


def test_one_step_cleanup_on_error(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test that cleanup (delete_simulation) runs even if observe fails."""
    monkeypatch.chdir(temp_workspace["root"])
    
    # Make observe raise an exception
    mock_k8s_deps["observe"].side_effect = Exception("K8s API error")
    
    # Should raise the exception but still call delete
    with pytest.raises(Exception, match="K8s API error"):
        one_step(
            trace_path=temp_workspace["trace_path"],
            namespace="test-ns",
            deploy="web",
            target=3,
            duration=10,
            seed=42
        )
    
    # Verify delete_simulation was still called (cleanup in finally block)
    mock_k8s_deps["delete"].assert_called_once()


def test_one_step_creates_directories(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test that one_step creates .tmp directory if it doesn't exist."""
    # Remove only the .tmp directory (runs is created at module import time)
    shutil.rmtree(temp_workspace["tmp_dir"])
    
    monkeypatch.chdir(temp_workspace["root"])
    mock_k8s_deps["observe"].return_value = {"ready": 3, "pending": 0, "total": 3}
    
    result = one_step(
        trace_path=temp_workspace["trace_path"],
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=10,
        seed=42
    )
    
    assert result["status"] == 0
    
    # Verify .tmp directory was created
    assert (temp_workspace["root"] / ".tmp").exists()
    
    # runs directory should already exist from module import
    assert (temp_workspace["root"] / "runs").exists()


def test_one_step_idempotency(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test that running one_step twice appends logs correctly."""
    monkeypatch.chdir(temp_workspace["root"])
    mock_k8s_deps["observe"].return_value = {"ready": 2, "pending": 1, "total": 3}
    
    # Run twice with same seed
    result1 = one_step(
        trace_path=temp_workspace["trace_path"],
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=10,
        seed=42
    )
    
    result2 = one_step(
        trace_path=temp_workspace["trace_path"],
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=10,
        seed=42
    )
    
    assert result1["status"] == result2["status"] == 0
    
    # Verify logs were appended (2 records)
    step_log = temp_workspace["root"] / "runs" / "step.jsonl"
    step_records = [json.loads(line) for line in step_log.read_text().strip().split('\n')]
    assert len(step_records) == 2
    
    # Both records should have same parameters
    assert step_records[0]["namespace"] == step_records[1]["namespace"] == "virtual-default"
    assert step_records[0]["seed"] == step_records[1]["seed"] == 42
    
    # Note: sim_name will differ because timestamp changes between calls
    # This is expected behavior - each run gets a unique timestamp
    assert step_records[0]["sim_name"].startswith("diag-")
    assert step_records[1]["sim_name"].startswith("diag-")
    
    # Summary should show 2 steps
    summary_log = temp_workspace["root"] / "runs" / "summary.json"
    summary = json.loads(summary_log.read_text())
    assert summary["total_steps"] == 2


def test_one_step_trace_not_found(temp_workspace, mock_k8s_deps, monkeypatch):
    """Test error handling when trace file doesn't exist."""
    monkeypatch.chdir(temp_workspace["root"])
    
    # Should raise FileNotFoundError
    with pytest.raises(FileNotFoundError):
        one_step(
            trace_path="nonexistent/trace.msgpack",
            namespace="test-ns",
            deploy="web",
            target=3,
            duration=10,
            seed=42
        )
    
    # Cleanup should still run
    mock_k8s_deps["delete"].assert_called_once()
