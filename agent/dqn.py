import random
import math
import os
from collections import deque, namedtuple

import torch
import torch.nn as nn
import torch.optim as optim

from .agent import BaseAgent


###############################################################################
# Q-Network
###############################################################################

class QNetwork(nn.Module):
    def __init__(self, state_dim, action_dim, hidden_dims=(24, 48)):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, hidden_dims[0]),
            nn.ReLU(),
            nn.Linear(hidden_dims[0], hidden_dims[1]),
            nn.ReLU(),
            nn.Linear(hidden_dims[1], action_dim)
        )

    def forward(self, x):
        return self.net(x)


###############################################################################
# Replay Memory
###############################################################################

Transition = namedtuple(
    "Transition", ("state", "action", "next_state", "reward", "done")
)


class ReplayMemory:
    def __init__(self, capacity):
        self.buffer = deque(maxlen=capacity)

    def push(self, *args):
        self.buffer.append(Transition(*args))

    def sample(self, batch_size):
        return random.sample(self.buffer, batch_size)

    def __len__(self):
        return len(self.buffer)


###############################################################################
# DQN Agent
###############################################################################

class DQNAgent(BaseAgent):
    def __init__(
        self,
        state_dim,
        n_actions,
        learning_rate=0.001,
        gamma=0.99,
        eps_start=1.0,
        eps_end=0.1,
        eps_decay_steps=1000,
        replay_buffer_size=10000,
        batch_size=32,
        target_update_freq=500,
        device=None
    ):
        self.state_dim = state_dim
        self.n_actions = n_actions
        self.gamma = gamma
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay_steps = eps_decay_steps
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        
        # Device setup
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = device

        # Networks
        self.q_net = QNetwork(state_dim, n_actions).to(self.device)
        self.target_net = QNetwork(state_dim, n_actions).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.target_net.eval()

        # Optimizer
        self.optimizer = optim.RMSprop(self.q_net.parameters(), lr=learning_rate)

        # Replay memory
        self.memory = ReplayMemory(replay_buffer_size)

        # Step counter
        self.total_steps = 0

    def _calculate_epsilon(self):
        """Calculate current epsilon value based on decay schedule."""
        if self.total_steps >= self.eps_decay_steps:
            return self.eps_end
        return self.eps_start - (self.eps_start - self.eps_end) * (
            self.total_steps / self.eps_decay_steps
        )

    def act(self, state):
        """Select action using epsilon-greedy policy."""
        epsilon = self._calculate_epsilon()
        
        # Exploration
        if random.random() < epsilon:
            return random.randrange(self.n_actions)
        
        # Exploitation
        if not isinstance(state, torch.Tensor):
            state = torch.tensor(state, dtype=torch.float32, device=self.device)
        
        if state.dim() == 1:
            state = state.unsqueeze(0)
        
        with torch.no_grad():
            q_values = self.q_net(state)
            return q_values.argmax(dim=1).item()

    def update(self, state, action, next_state, reward, done):
        """Store transition and perform learning update if enough samples."""
        # Convert to tensors
        if not isinstance(state, torch.Tensor):
            state = torch.tensor(state, dtype=torch.float32, device=self.device)
        if not isinstance(next_state, torch.Tensor):
            next_state = torch.tensor(next_state, dtype=torch.float32, device=self.device)
        
        if state.dim() == 1:
            state = state.unsqueeze(0)
        if next_state.dim() == 1:
            next_state = next_state.unsqueeze(0)
        
        action_tensor = torch.tensor([[action]], device=self.device)
        reward_tensor = torch.tensor([reward], dtype=torch.float32, device=self.device)
        done_tensor = torch.tensor([done], dtype=torch.bool, device=self.device)

        # Store transition
        self.memory.push(state, action_tensor, next_state, reward_tensor, done_tensor)

        # Increment step counter
        self.total_steps += 1

        # Perform learning update if we have enough samples
        if len(self.memory) >= self.batch_size:
            self._train_step()

        # Update target network periodically
        if self.total_steps % self.target_update_freq == 0:
            self.target_net.load_state_dict(self.q_net.state_dict())

    def _train_step(self):
        """Sample from replay buffer and perform one training step."""
        minibatch = self.memory.sample(self.batch_size)
        batch = Transition(*zip(*minibatch))

        state_batch = torch.cat(batch.state)
        action_batch = torch.cat(batch.action)
        reward_batch = torch.cat(batch.reward)
        next_state_batch = torch.cat(batch.next_state)
        done_batch = torch.cat(batch.done)

        # Compute Q(s, a)
        q_values = self.q_net(state_batch).gather(1, action_batch)

        # Compute max Q(s', a')
        next_q_values = torch.zeros(self.batch_size, 1, device=self.device)
        non_terminal_mask = ~done_batch

        if non_terminal_mask.any():
            with torch.no_grad():
                next_q_values[non_terminal_mask] = (
                    self.target_net(next_state_batch[non_terminal_mask])
                    .max(1)[0]
                    .unsqueeze(1)
                )

        # Compute target: r + gamma * max Q(s', a')
        target = reward_batch.unsqueeze(1) + self.gamma * next_q_values

        # Compute loss and update
        loss = nn.MSELoss()(q_values, target)

        self.optimizer.zero_grad()
        loss.backward()
        self.optimizer.step()

    def save(self, path: str):
        """
        Save the DQN agent checkpoint.
        Saves Q-network, Target network, Optimizer, and Total Steps.
        """
        checkpoint = {
            'q_net_state_dict': self.q_net.state_dict(),
            'target_net_state_dict': self.target_net.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'total_steps': self.total_steps,
            'hyperparams': {
                'state_dim': self.state_dim,
                'n_actions': self.n_actions,
                'gamma': self.gamma,
                'eps_start': self.eps_start,
                'eps_end': self.eps_end,
                'eps_decay_steps': self.eps_decay_steps
            }
        }
        torch.save(checkpoint, path)
        print(f"Saved DQN agent to {path}")

    def load(self, path: str):
        """
        Load the DQN agent checkpoint.
        """
        if not os.path.exists(path):
            raise FileNotFoundError(f"No checkpoint found at {path}")

        checkpoint = torch.load(path, map_location=self.device)
        
        self.q_net.load_state_dict(checkpoint['q_net_state_dict'])
        self.target_net.load_state_dict(checkpoint['target_net_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.total_steps = checkpoint['total_steps']
        
        # Optional: verify hyperparameters match
        saved_params = checkpoint.get('hyperparams', {})
        if saved_params.get('n_actions') != self.n_actions:
            print("Warning: Loaded agent has different number of actions than current configuration.")
            
        print(f"Loaded DQN agent from {path} (steps={self.total_steps})")

    def reset(self):
        """Reset agent (useful for multi-environment training)."""
        pass
    
    def visualize(self, save_path=None):
        """Visualize the DQN Q-values for a sweep of representative states."""
        import matplotlib.pyplot as plt
        import torch
        import numpy as np

        # Baseline features: CPU=500m, Mem=512Mi, Pending=0
        baseline_cpu = 500
        baseline_mem = 512
        pending = 0
        
        # Sweep replicas from 1 to 5 to see how the network reacts
        replicas_sweep = list(range(1, 6))
        states = []
        for r in replicas_sweep:
            states.append([baseline_cpu, baseline_mem, r, pending])
            
        states_tensor = torch.tensor(states, dtype=torch.float32, device=self.device)
        
        with torch.no_grad():
            q_values = self.q_net(states_tensor).cpu().numpy()
            
        fig, ax = plt.subplots(figsize=(8, 6))
        cax = ax.imshow(q_values, aspect='auto', cmap='viridis')
        fig.colorbar(cax, label='Estimated Q-Value')
        
        # Label axes
        ax.set_xticks(range(self.n_actions))
        ax.set_xticklabels([f"Action {i}" for i in range(self.n_actions)])
        ax.set_yticks(range(len(replicas_sweep)))
        ax.set_yticklabels([f"Rep={r}" for r in replicas_sweep])
        
        # Annotate text on the heatmap for exact values
        for i in range(len(replicas_sweep)):
            for j in range(self.n_actions):
                # Choose text color based on background intensity for readability
                color = "black" if q_values[i, j] > (np.max(q_values) + np.min(q_values)) / 2 else "white"
                ax.text(j, i, f"{q_values[i, j]:.2f}", ha="center", va="center", color=color)
                
        plt.xlabel('Actions')
        plt.ylabel('State (Varying Replicas)')
        plt.title('DQN Q-Value Heatmap (Fixed CPU/Mem/Pending)')
        
        if save_path:
            plt.savefig(save_path)
            print(f"Saved DQN visualization to {save_path}")
        else:
            plt.show()
        plt.close()
        
    def __repr__(self):
        return f"DQNAgent(state_dim={self.state_dim}, n_actions={self.n_actions})"