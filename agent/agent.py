"""
agent/agent.py

Agent factory — wraps DQN, Epsilon-Greedy, Random, and LLM agents
behind a single unified Agent class.

Changes from original:
  - Added AgentType.LLM
  - LLM branch takes 'provider' (LLMProvider) and 'mcp_client' (MCPClientSync)
  - All existing agent types and their interfaces are unchanged
"""

from __future__ import annotations

import logging
from enum import Enum
from typing import Any

logger = logging.getLogger("agent")


# Action names for visualization (must match ACTION_SPACE in runner/one_step.py)
ACTION_NAMES = ["noop", "+CPU", "+Mem", "+Rep", "-CPU", "-Mem", "-Rep"]

class AgentType(Enum):
    DQN            = "dqn"
    EPSILON_GREEDY = "greedy"
    RANDOM         = "random"
    LLM            = "llm"


class Agent:
    """
    Unified Agent interface.

    All agent types expose:
        act(...)                  → int
        update(...)               → None
        save(path)                → None
        load(path)                → None
        reset()                   → None
        visualize(...)            → None  (no-op where not applicable)
        plot_learning_curve(...)  → None  (no-op where not applicable)

    For AgentType.LLM the following kwargs are required:
        provider   (LLMProvider)    — from agent.providers.make_provider()
        mcp_client (MCPClientSync)  — must already be started
    """

    def __init__(self, agent_type: AgentType, **kwargs: Any) -> None:
        self._type  = agent_type
        self._agent = self._build(agent_type, **kwargs)

    @staticmethod
    def _build(agent_type: AgentType, **kwargs) -> Any:
        if agent_type == AgentType.DQN:
            from agent.dqn import DQNAgent
            return DQNAgent(
                state_dim          = kwargs.get("state_dim", 5),
                n_actions          = kwargs.get("n_actions", 7),
                learning_rate      = kwargs.get("learning_rate", 0.001),
                gamma              = kwargs.get("gamma", 0.97),
                eps_start          = kwargs.get("eps_start", 1.0),
                eps_end            = kwargs.get("eps_end", 0.1),
                eps_decay_steps    = kwargs.get("eps_decay_steps", 1000),
                replay_buffer_size = kwargs.get("replay_buffer_size", 2000),
                batch_size         = kwargs.get("batch_size", 32),
                target_update_freq = kwargs.get("target_update_freq", 50),
            )

        elif agent_type == AgentType.EPSILON_GREEDY:
            from agent.eps_greedy import EpsilonGreedyAgent
            return EpsilonGreedyAgent(
                n_actions = kwargs.get("n_actions", 7),
                epsilon   = kwargs.get("epsilon", 0.1),
            )

        elif agent_type == AgentType.RANDOM:
            from agent.eps_greedy import EpsilonGreedyAgent
            return EpsilonGreedyAgent(
                n_actions = kwargs.get("n_actions", 7),
                epsilon   = 1.0,
            )

        elif agent_type == AgentType.LLM:
            from agent.llm_agent import LLMAgent
            provider   = kwargs.get("provider")
            mcp_client = kwargs.get("mcp_client")
            if provider is None:
                raise ValueError(
                    "AgentType.LLM requires a 'provider' (LLMProvider) kwarg. "
                    "Use agent.providers.make_provider(provider_name, model) to create one."
                )
            if mcp_client is None:
                raise ValueError(
                    "AgentType.LLM requires an 'mcp_client' (MCPClientSync) kwarg."
                )
            return LLMAgent(
                provider        = provider,
                mcp_client      = mcp_client,
                max_tool_rounds = kwargs.get("max_tool_rounds", 8),
            )

        else:
            raise ValueError(f"Unknown AgentType: {agent_type}")

    # ---- public interface -------------------------------------------------

    def act(self, *args: Any, **kwargs: Any) -> int:
        return self._agent.act(*args, **kwargs)

    def update(self, *args: Any, **kwargs: Any) -> None:
        self._agent.update(*args, **kwargs)

    def save(self, path: str) -> None:
        self._agent.save(path)

    def load(self, path: str) -> None:
        self._agent.load(path)

    def reset(self) -> None:
        if hasattr(self._agent, "reset"):
            self._agent.reset()

    def visualize(self, save_path: str = "", **kwargs: Any) -> None:
        if hasattr(self._agent, "visualize"):
            self._agent.visualize(save_path=save_path, **kwargs)

    def plot_learning_curve(self, save_path: str = "", **kwargs: Any) -> None:
        if hasattr(self._agent, "plot_learning_curve"):
            self._agent.plot_learning_curve(save_path=save_path, **kwargs)

    @property
    def episode_reward_history(self) -> list:
        return getattr(self._agent, "episode_reward_history", [])

    @property
    def current_episode_reward(self) -> float:
        return getattr(self._agent, "current_episode_reward", 0.0)

    @current_episode_reward.setter
    def current_episode_reward(self, value: float) -> None:
        if hasattr(self._agent, "current_episode_reward"):
            self._agent.current_episode_reward = value

    def _train_step(self) -> None:
        if hasattr(self._agent, "_train_step"):
            self._agent._train_step()
