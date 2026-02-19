import random
import json
import os
from .agent import BaseAgent


class EpsilonGreedyAgent(BaseAgent):
    def __init__(self, n_actions, epsilon=0.1):
        self.n_actions = n_actions
        self.epsilon = epsilon

        self.counts = [0 for _ in range(n_actions)]
        self.values = [0.0 for _ in range(n_actions)]

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
            "values": self.values
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
        
        self.n_actions = data["n_actions"]
        self.epsilon = data["epsilon"]
        self.counts = data["counts"]
        self.values = data["values"]
        print(f"Loaded EpsilonGreedy agent from {path}")

    def reset(self):
        """Reset counts and values."""
        self.counts = [0 for _ in range(self.n_actions)]
        self.values = [0.0 for _ in range(self.n_actions)]
    
    def __repr__(self):
        return f"EpsilonGreedyAgent(n_actions={self.n_actions}, epsilon={self.epsilon})"