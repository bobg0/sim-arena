"""Tests for agent module."""

import pytest
from agent.agent import Agent, AgentType, create_epsilon_greedy_agent


def test_agent_epsilon_greedy_creation():
    """Test creating epsilon-greedy agent."""
    agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
    assert agent.n_actions == 4


def test_agent_epsilon_greedy_act_returns_index():
    """Test act() returns valid action index."""
    agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
    action_idx = agent.act()
    assert isinstance(action_idx, int)
    assert 0 <= action_idx < 4


def test_agent_epsilon_greedy_update():
    """Test update() runs without error."""
    agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.0)  # No exploration
    action_idx = agent.act()
    agent.update(action_idx, 1.0)
    # After update, values should change
    agent.update(action_idx, 0.5)


def test_agent_epsilon_greedy_reset():
    """Test reset() clears state."""
    agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
    agent.act()
    agent.update(0, 1.0)
    agent.reset()
    # After reset, act should still work
    action_idx = agent.act()
    assert 0 <= action_idx < 4


def test_create_epsilon_greedy_agent():
    """Test convenience function creates agent."""
    agent = create_epsilon_greedy_agent(n_actions=4, epsilon=0.2)
    assert agent.n_actions == 4
    action_idx = agent.act()
    assert 0 <= action_idx < 4


def test_agent_epsilon_zero_exploits():
    """Test with epsilon=0, agent exploits (always picks same after updates)."""
    agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.0)
    # Initial values are 0, so any action is equally good
    action1 = agent.act()
    agent.update(1, 1.0)  # Make action 1 best
    action2 = agent.act()
    # With epsilon=0, after update, action 1 should be preferred
    # (may still be random on first call before any update)
    agent.update(1, 1.0)
    action3 = agent.act()
    assert action3 == 1  # Should exploit action 1
