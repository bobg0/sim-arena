"""
Agent module for reinforcement learning.
"""


from .eps_greedy import EpsilonGreedyAgent
from .dqn import DQNAgent

__all__ = [
    'Agent',
    'AgentType',
    'EpsilonGreedyAgent',
    'DQNAgent'
]