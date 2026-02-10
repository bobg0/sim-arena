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
        """
        Select an action given the current state.
        
        Args:
            state: Current state (format depends on agent type)
        
        Returns:
            action: Selected action (integer)
        """
        pass
    
    @abstractmethod
    def update(self, *args, **kwargs):
        """
        Update agent's internal state/model.
        
        Args vary by agent type.
        """
        pass
    
    def reset(self):
        """Reset agent state (optional, override if needed)."""
        pass


class Agent:
    """
    Unified wrapper class for different RL agents.
    
    This class provides a consistent interface for both simple agents
    (like EpsilonGreedy) and complex agents (like DQN).
    
    Usage:
        # Create an epsilon-greedy agent
        agent = Agent(AgentType.EPSILON_GREEDY, n_actions=4, epsilon=0.1)
        
        # Create a DQN agent
        agent = Agent(AgentType.DQN, state_dim=4, n_actions=2, gamma=0.99)
        
        # Use the agent
        action = agent.act(state)
        agent.update(state, action, next_state, reward, done)
    """
    
    def __init__(self, agent_type: Union[AgentType, str], **kwargs):
        """
        Initialize agent wrapper.
        
        Args:
            agent_type: Type of agent to create (AgentType enum or string)
            **kwargs: Agent-specific parameters
        """
        # Convert string to AgentType if needed
        if isinstance(agent_type, str):
            agent_type = AgentType(agent_type.lower())
        
        self.agent_type = agent_type
        self._agent = self._create_agent(**kwargs)
    
    def _create_agent(self, **kwargs) -> BaseAgent:
        """
        Factory method to create the appropriate agent.
        
        Args:
            **kwargs: Agent-specific parameters
        
        Returns:
            Agent instance
        """
        if self.agent_type == AgentType.EPSILON_GREEDY:
            from .eps_greedy import EpsilonGreedyAgent
            return EpsilonGreedyAgent(**kwargs)
        
        elif self.agent_type == AgentType.DQN:
            from .dqn import DQNAgent
            return DQNAgent(**kwargs)
        
        else:
            raise ValueError(f"Unknown agent type: {self.agent_type}")
    
    def act(self, state: Any = None) -> int:
        """
        Select an action.
        
        Args:
            state: Current state (required for DQN, optional for EpsilonGreedy)
        
        Returns:
            action: Selected action (integer)
        """
        if self.agent_type == AgentType.EPSILON_GREEDY:
            # EpsilonGreedy doesn't use state
            return self._agent.act()
        else:
            # DQN requires state
            if state is None:
                raise ValueError("State is required for DQN agent")
            return self._agent.act(state)
    
    def update(self, *args, **kwargs):
        """
        Update the agent.
        
        For EpsilonGreedy:
            update(action, reward)
        
        For DQN:
            update(state, action, next_state, reward, done)
        """
        self._agent.update(*args, **kwargs)
    
    def reset(self):
        """Reset agent state."""
        if hasattr(self._agent, 'reset'):
            self._agent.reset()
    
    @property
    def n_actions(self) -> int:
        """Get number of actions."""
        return self._agent.n_actions
    
    def get_agent(self):
        """
        Get the underlying agent instance.
        
        Useful for accessing agent-specific methods or attributes.
        
        Returns:
            The underlying agent instance
        """
        return self._agent
    
    def __repr__(self) -> str:
        return f"Agent(type={self.agent_type.value}, underlying={self._agent})"


###############################################################################
# Convenience functions
###############################################################################

def create_epsilon_greedy_agent(n_actions: int, epsilon: float = 0.1) -> Agent:
    """
    Convenience function to create an epsilon-greedy agent.
    
    Args:
        n_actions: Number of available actions
        epsilon: Exploration probability (default: 0.1)
    
    Returns:
        Agent wrapper around EpsilonGreedyAgent
    """
    return Agent(AgentType.EPSILON_GREEDY, n_actions=n_actions, epsilon=epsilon)


def create_dqn_agent(
    state_dim: int,
    n_actions: int,
    learning_rate: float = 0.001,
    gamma: float = 0.99,
    eps_start: float = 1.0,
    eps_end: float = 0.1,
    eps_decay_steps: int = 1000,
    **kwargs
) -> Agent:
    """
    Convenience function to create a DQN agent.
    
    Args:
        state_dim: Dimension of state space
        n_actions: Number of available actions
        learning_rate: Learning rate for optimizer (default: 0.001)
        gamma: Discount factor (default: 0.99)
        eps_start: Starting epsilon value (default: 1.0)
        eps_end: Final epsilon value (default: 0.1)
        eps_decay_steps: Steps to decay epsilon (default: 1000)
        **kwargs: Additional DQN parameters
    
    Returns:
        Agent wrapper around DQNAgent
    """
    return Agent(
        AgentType.DQN,
        state_dim=state_dim,
        n_actions=n_actions,
        learning_rate=learning_rate,
        gamma=gamma,
        eps_start=eps_start,
        eps_end=eps_end,
        eps_decay_steps=eps_decay_steps,
        **kwargs
    )