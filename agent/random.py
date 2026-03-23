"""
Random baseline agent for reinforcement learning.
"""
import random
import json
import os
from .agent import Agent

class RandomAgent(Agent):
    def __init__(self, n_actions: int, **kwargs):
        self.n_actions = n_actions
        self.reward_history = []
        
        # Track episode returns to match DQN agent
        self.episode_reward_history = []
        self.current_episode_reward = 0.0

    def act(self, state=None) -> int:
        """Select an action uniformly at random."""
        return random.randrange(self.n_actions)

    def update(self, state, action, next_state, reward, done, *args, **kwargs):
        """Track reward history and episode returns for the learning curve plotting."""
        self.reward_history.append(float(reward))
        
        # Accumulate episodic return
        self.current_episode_reward += float(reward)
        if done:
            self.episode_reward_history.append(self.current_episode_reward)
            self.current_episode_reward = 0.0

    def save(self, path: str):
        """Save agent state (reward history) to a JSON file."""
        data = {
            "n_actions": self.n_actions,
            "reward_history": self.reward_history,
            "episode_reward_history": self.episode_reward_history,
            "current_episode_reward": self.current_episode_reward
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
        self.episode_reward_history = data.get("episode_reward_history", [])
        self.current_episode_reward = data.get("current_episode_reward", 0.0)
        print(f"Loaded Random agent from {path}")

    def reset(self):
        """Reset reward history."""
        self.reward_history = []
        self.episode_reward_history = []
        self.current_episode_reward = 0.0

    def plot_learning_curve(self, save_path=None):
        """Plot the episodic return and moving average of rewards over time."""
        import matplotlib.pyplot as plt
        import numpy as np
        
        fig, axes = plt.subplots(2, 1, figsize=(10, 7))
        
        # Plot 1: Episode returns (cumulative across all episodes)
        ax = axes[0]
        if len(self.episode_reward_history) > 0:
            episodes = np.arange(1, len(self.episode_reward_history) + 1)
            ax.plot(episodes, self.episode_reward_history, marker='o', markersize=8, alpha=0.7, color='blue', label='Total Episode Return')
            if len(self.episode_reward_history) >= 3:
                window = min(10, len(self.episode_reward_history))
                rolling_rewards = np.convolve(self.episode_reward_history, np.ones(window)/window, mode='valid')
                ax.plot(episodes[window-1:], rolling_rewards, color='darkblue', linewidth=2, label=f'{window}-Ep Moving Avg')
            ax.set_title('Random Agent: Episodic Return')
            ax.set_xlabel('Episode')
            ax.set_ylabel('Return')
            ax.set_xlim(0.5, len(self.episode_reward_history) + 0.5)
            ax.legend()
        else:
            ax.set_title('Random Agent: Episodic Return (No Episode Data Yet)')
        ax.grid(alpha=0.3)

        # Plot 2: Step rewards (per-step feedback)
        ax = axes[1]
        if len(self.reward_history) > 0:
            window = min(100, len(self.reward_history))
            rolling = np.convolve(self.reward_history, np.ones(window)/window, mode='valid')
            ax.plot(self.reward_history, alpha=0.3, color='green', label='Step Reward')
            ax.plot(np.arange(window-1, len(self.reward_history)), rolling, color='darkgreen', linewidth=2, label=f'{window}-Step Moving Avg')
            ax.set_title('Random Agent: Step Rewards')
            ax.set_xlabel('Training Steps')
            ax.set_ylabel('Reward')
            ax.legend()
        else:
            ax.set_title('Random Agent: Step Rewards (No Data Yet)')
        ax.grid(alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path)
            print(f"Saved learning curve to {save_path}")
        else:
            plt.show()
        plt.close()

    def __repr__(self):
        return f"RandomAgent(n_actions={self.n_actions})"