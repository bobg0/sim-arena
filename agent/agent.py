"""
Base agent class and unified wrapper for different RL agents.
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Optional, Union


class AgentType(Enum):
    """Enumeration of available agent types."""
    EPSILON_GREEDY = "epsilon_greedy"
    DQN = "dqn"


class BaseAgent(ABC):
    """Abstract base class for all agents."""
    
    @abstractmethod
    def act(self, state: Any) -> int:
        """Select an action given the current state."""
        pass
    
    @abstractmethod
    def update(self, *args, **kwargs):
        """Update agent's internal state/model."""
        pass
    
    @abstractmethod
    def save(self, path: str):
        """Save the agent's state to a file."""
        pass

    @abstractmethod
    def load(self, path: str):
        """Load the agent's state from a file."""
        pass
    
    def reset(self):
        """Reset agent state (optional, override if needed)."""
        pass


class Agent:
    """
    Unified wrapper class for different RL agents.
    """
    
    def __init__(self, agent_type: Union[AgentType, str], **kwargs):
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type.lower())
        
        self.agent_type = agent_type
        self._agent = self._create_agent(**kwargs)
    
    def _create_agent(self, **kwargs) -> BaseAgent:
        if self.agent_type == AgentType.EPSILON_GREEDY:
            from .eps_greedy import EpsilonGreedyAgent
            return EpsilonGreedyAgent(**kwargs)
        elif self.agent_type == AgentType.DQN:
            from .dqn import DQNAgent
            return DQNAgent(**kwargs)
        else:
            raise ValueError(f"Unknown agent type: {self.agent_type}")
    
    def act(self, state: Any = None) -> int:
        if self.agent_type == AgentType.EPSILON_GREEDY:
            return self._agent.act()
        else:
            if state is None:
                raise ValueError("State is required for DQN agent")
            return self._agent.act(state)
    
    def update(self, *args, **kwargs):
        self._agent.update(*args, **kwargs)
    
    def save(self, path: str):
        """Save the underlying agent to the specified path."""
        self._agent.save(path)

    def load(self, path: str):
        """Load the underlying agent from the specified path."""
        self._agent.load(path)
    
    def reset(self):
        if hasattr(self._agent, 'reset'):
            self._agent.reset()
    
    @property
    def n_actions(self) -> int:
        return self._agent.n_actions
    
    def get_agent(self):
        return self._agent
    
    def __repr__(self) -> str:
        return f"Agent(type={self.agent_type.value}, underlying={self._agent})"