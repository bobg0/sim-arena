import random
import json
import os
from .agent import BaseAgent, ACTION_NAMES


class EpsilonGreedyAgent(BaseAgent):
    def __init__(self, n_actions, epsilon=0.1):
        self.n_actions = n_actions
        self.epsilon = epsilon

        self.counts = [0 for _ in range(n_actions)]
        self.values = [0.0 for _ in range(n_actions)]
        self.reward_history = []

    def act(self, state=None):
        # exploration
        if random.random() < self.epsilon:
            return random.randrange(self.n_actions)

        # exploitation (break ties randomly)
        max_value = max(self.values)
        best_actions = [
            i for i, v in enumerate(self.values) if v == max_value
        ]
        return random.choice(best_actions)

    def update(self, action, reward):
        self.reward_history.append(float(reward))
        self.counts[action] += 1
        n = self.counts[action]

        # incremental average
        old_value = self.values[action]
        self.values[action] = old_value + (reward - old_value) / n
    
    def save(self, path: str):
        """Save agent state (counts and values) to a JSON file."""
        data = {
            "n_actions": self.n_actions,
            "epsilon": self.epsilon,
            "counts": self.counts,
            "values": self.values,
            "reward_history": self.reward_history
        }
        with open(path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"Saved EpsilonGreedy agent to {path}")

    def load(self, path: str):
        """Load agent state from a JSON file."""
        if not os.path.exists(path):
            raise FileNotFoundError(f"No agent file found at {path}")
            
        with open(path, 'r') as f:
            data = json.load(f)
        
        self.n_actions = data.get("n_actions", self.n_actions)
        self.epsilon = data.get("epsilon", self.epsilon)
        self.counts = data.get("counts", self.counts)
        self.values = data.get("values", self.values)
        self.reward_history = data.get("reward_history", [])
        print(f"Loaded EpsilonGreedy agent from {path}")

    def reset(self):
        """Reset counts, values, and history."""
        self.counts = [0 for _ in range(self.n_actions)]
        self.values = [0.0 for _ in range(self.n_actions)]
        self.reward_history = []
    
    def visualize(self, save_path=None):
        """Visualize the learned Q-values as a bar chart."""
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(10, 5))
        actions = list(range(self.n_actions))
        labels = ACTION_NAMES[:self.n_actions] if self.n_actions <= len(ACTION_NAMES) else [f"A{i}" for i in range(self.n_actions)]
        plt.bar(actions, self.values, color='skyblue', edgecolor='black')
        
        plt.xlabel('Action')
        plt.ylabel('Estimated Q-Value')
        plt.title(f'Epsilon-Greedy Q-Values (epsilon={self.epsilon:.2f})')
        plt.xticks(actions, labels, rotation=45, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.7)
        
        if save_path:
            plt.savefig(save_path)
            print(f"Saved visualization to {save_path}")
        else:
            plt.show()
        plt.close()

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
            
        plt.title(f'Epsilon-Greedy Learning Curve (epsilon={self.epsilon:.2f})')
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
        return f"EpsilonGreedyAgent(n_actions={self.n_actions}, epsilon={self.epsilon})"