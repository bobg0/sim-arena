"""
Agent module for reinforcement learning.
"""

from .agent import Agent, AgentType
from .eps_greedy import EpsilonGreedyAgent
from .random import RandomAgent

try:
    from .dqn import DQNAgent
except Exception:  # pragma: no cover - optional heavy dependency
    DQNAgent = None

__all__ = [
    'Agent',
    'AgentType',
    'EpsilonGreedyAgent',
    'DQNAgent',
    'RandomAgent'
]
