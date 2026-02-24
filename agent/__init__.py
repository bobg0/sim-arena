"""
Agent module for reinforcement learning.
"""

from .eps_greedy import EpsilonGreedyAgent
from .dqn import DQNAgent
from .random import RandomAgent

__all__ = [
    'Agent',
    'AgentType',
    'EpsilonGreedyAgent',
    'DQNAgent',
    'RandomAgent'
]