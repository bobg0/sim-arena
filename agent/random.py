"""
Random baseline agent for reinforcement learning.
"""
import random
import json
import os
from .agent import BaseAgent

class RandomAgent(BaseAgent):
    def __init__(self, n_actions: int, **kwargs):
        self.n_actions = n_actions
        self.reward_history = []

    def act(self, state=None) -> int:
        """Select an action uniformly at random."""
        return random.randrange(self.n_actions)

    def update(self, action, reward, *args, **kwargs):
        """Track reward history for the learning curve plotting."""
        self.reward_history.append(float(reward))

    def save(self, path: str):
        """Save agent state (reward history) to a JSON file."""
        data = {
            "n_actions": self.n_actions,
            "reward_history": self.reward_history
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved Random agent to {path}")

    def load(self, path: str):
        """Load agent state from a JSON file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"No agent file found at {path}")
            
        with open(path, 'r') as f:
            data = json.load(f)
        
        self.n_actions = data.get("n_actions", self.n_actions)
        self.reward_history = data.get("reward_history", [])
        print(f"Loaded Random agent from {path}")

    def reset(self):
        """Reset reward history."""
        self.reward_history = []

    def plot_learning_curve(self, save_path=None):
        """Plot the moving average of rewards over time."""
        import matplotlib.pyplot as plt
        import numpy as np
        
        plt.figure(figsize=(10, 5))
        if len(self.reward_history) > 0:
            window = min(100, len(self.reward_history))
            rolling_rewards = np.convolve(self.reward_history, np.ones(window)/window, mode='valid')
            plt.plot(self.reward_history, alpha=0.3, color='blue', label='Raw Step Reward')
            plt.plot(np.arange(window-1, len(self.reward_history)), rolling_rewards, color='darkblue', label=f'{window}-Step Moving Avg')
            
        plt.title('Random Agent Learning Curve (Baseline)')
        plt.xlabel('Steps')
        plt.ylabel('Reward')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        if save_path:
            plt.savefig(save_path)
            print(f"Saved learning curve to {save_path}")
        else:
            plt.show()
        plt.close()

    def __repr__(self):
        return f"RandomAgent(n_actions={self.n_actions})"