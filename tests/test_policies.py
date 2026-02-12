"""Tests for runner/policies.py"""

import pytest
from runner.policies import get_policy, POLICY_REGISTRY


def test_get_policy_all_registered():
    """Test that all registered policies can be retrieved."""
    for name in POLICY_REGISTRY:
        policy = get_policy(name)
        assert callable(policy)


def test_get_policy_unknown():
    """Test get_policy raises for unknown name."""
    with pytest.raises(ValueError, match="Unknown policy"):
        get_policy("nonexistent")


def test_policy_noop():
    """Test noop always returns noop action."""
    policy = get_policy("noop")
    action = policy(obs={"ready": 0, "pending": 3, "total": 3}, deploy="web")
    assert action["type"] == "noop"


def test_policy_heuristic_pending():
    """Test heuristic bumps CPU when pending > 0."""
    policy = get_policy("heuristic")
    action = policy(obs={"ready": 2, "pending": 1, "total": 3}, deploy="web")
    assert action["type"] == "bump_cpu_small"
    assert action.get("deploy") == "web"


def test_policy_heuristic_no_pending():
    """Test heuristic returns noop when pending == 0."""
    policy = get_policy("heuristic")
    action = policy(obs={"ready": 3, "pending": 0, "total": 3}, deploy="web")
    assert action["type"] == "noop"


def test_policy_bump_cpu():
    """Test bump_cpu always returns bump_cpu_small."""
    policy = get_policy("bump_cpu")
    action = policy(obs={"ready": 3, "pending": 0, "total": 3}, deploy="web")
    assert action["type"] == "bump_cpu_small"
    assert action["deploy"] == "web"


def test_policy_bump_mem():
    """Test bump_mem always returns bump_mem_small."""
    policy = get_policy("bump_mem")
    action = policy(obs={"ready": 0, "pending": 3, "total": 3}, deploy="api")
    assert action["type"] == "bump_mem_small"
    assert action["deploy"] == "api"


def test_policy_scale_replicas():
    """Test scale_replicas returns scale_up_replicas with delta."""
    policy = get_policy("scale_replicas")
    action = policy(obs={"ready": 2, "pending": 0, "total": 2}, deploy="web")
    assert action["type"] == "scale_up_replicas"
    assert action["deploy"] == "web"
    assert action["delta"] == 1


def test_policy_random_returns_valid_action():
    """Test random policy returns one of the valid action types."""
    policy = get_policy("random")
    valid_types = {"noop", "bump_cpu_small", "bump_mem_small", "scale_up_replicas"}
    for _ in range(20):
        action = policy(obs={"ready": 2, "pending": 1, "total": 3}, deploy="web")
        assert action["type"] in valid_types
        if action["type"] != "noop":
            assert action.get("deploy") == "web"
