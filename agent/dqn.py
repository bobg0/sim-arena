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
        gamma=0.97,
        eps_start=1.0,
        eps_end=0.1,
        eps_decay_steps=1000,
        replay_buffer_size=2000,
        batch_size=32,
        target_update_freq=50,
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

        # Metrics tracking
        self.total_steps = 0
        self.reward_history = []
        self.loss_history = []
        
        # Variable-length episode tracking
        self.current_episode_reward = 0.0
        self.episode_reward_history = []

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
            # Set to eval mode so BatchNorm doesn't crash on batch_size=1
            self.q_net.eval()
            q_values = self.q_net(state)
            self.q_net.train()
            return q_values.argmax(dim=1).item()

    def update(self, state, action, next_state, reward, done):
        """Store transition and perform learning update if enough samples."""
        self.reward_history.append(float(reward))
        
        # Track true episode returns
        self.current_episode_reward += float(reward)
        if done:
            self.episode_reward_history.append(self.current_episode_reward)
            self.current_episode_reward = 0.0

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
        self.loss_history.append(float(loss.item()))

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
            'reward_history': self.reward_history,
            'loss_history': self.loss_history,
            'episode_reward_history': self.episode_reward_history,
            'current_episode_reward': self.current_episode_reward,
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
        self.reward_history = checkpoint.get('reward_history', [])
        self.loss_history = checkpoint.get('loss_history', [])
        
        # Safely load the new keys (defaults to empty/0 if loading an older checkpoint)
        self.episode_reward_history = checkpoint.get('episode_reward_history', [])
        self.current_episode_reward = checkpoint.get('current_episode_reward', 0.0)
        
        # Optional: verify hyperparameters match
        saved_params = checkpoint.get('hyperparams', {})
        if saved_params.get('n_actions') != self.n_actions:
            print("Warning: Loaded agent has different number of actions than current configuration.")
            
        print(f"Loaded DQN agent from {path} (steps={self.total_steps})")

    def reset(self):
        """Reset agent (useful for multi-environment training)."""
        self.reward_history = []
        self.loss_history = []
        self.episode_reward_history = []
        self.current_episode_reward = 0.0
    
    def visualize(self, save_path=None):
        """Visualize the DQN Q-values for a sweep of representative states across 4 subplots."""
        import matplotlib.pyplot as plt

        # Define configurations for the 4 subplots (Low/High CPU and Low/High Mem)
        configs = [
            {"title": "Low CPU / Low Mem", "cpu": 500, "mem": 512},
            {"title": "High CPU / Low Mem", "cpu": 2000, "mem": 512},
            {"title": "Low CPU / High Mem", "cpu": 500, "mem": 2048},
            {"title": "High CPU / High Mem", "cpu": 2000, "mem": 2048}
        ]

        # Constants for the sweep
        # replicas = 2
        pending = 0
        distance_sweep = list(range(5))  # Sweeps distances 0 through 4
        
        # Set up a 2x2 grid of subplots
        fig, axes = plt.subplots(2, 2, figsize=(14, 10))
        fig.suptitle('DQN Q-Value Heatmaps: Resource Combinations (Pending: 0)', fontsize=16)
        
        # Flatten axes array for easy iteration
        axes = axes.flatten()

        # Set to eval mode for visualization so BatchNorm statistics don't distort on small batches
        self.q_net.eval()

        for idx, config in enumerate(configs):
            ax = axes[idx]
            states = []
            
            # Build state tensors for this specific subplot's CPU/Mem config
            for d in distance_sweep:
                states.append([config["cpu"], config["mem"], pending, d])
                
            states_tensor = torch.tensor(states, dtype=torch.float32, device=self.device)
            
            with torch.no_grad():
                q_values = self.q_net(states_tensor).cpu()

            q_min = torch.min(q_values)
            q_max = torch.max(q_values)
            
            if q_max == q_min:
                threshold = q_max
            else:
                threshold = (q_max + q_min) / 2

            cax = ax.imshow(q_values, aspect='auto', cmap='viridis')
            fig.colorbar(cax, ax=ax, label='Estimated Q-Value')
            
            # Label axes
            ax.set_xticks(range(self.n_actions))
            ax.set_xticklabels([f"Action {i}" for i in range(self.n_actions)])
            ax.set_yticks(range(len(distance_sweep)))
            ax.set_yticklabels([f"Dist={r}" for r in distance_sweep])
            
            # Annotate text on the heatmap for exact values
            for i in range(len(distance_sweep)):
                for j in range(self.n_actions):
                    val = q_values[i, j]
                    color = "black" if val > threshold else "white"
                    ax.text(j, i, f"{val.item():.2f}", ha="center", va="center", color=color)
                    
            ax.set_xlabel('Actions')
            ax.set_ylabel('Distance')
            ax.set_title(f"{config['title']}\n(CPU: {config['cpu']}m / Mem: {config['mem']}Mi)")

        # Restore training mode
        self.q_net.train()

        # Adjust layout so the suptitle and subplots don't overlap
        plt.tight_layout(rect=[0, 0.03, 1, 0.95])
        
        if save_path:
            plt.savefig(save_path)
            print(f"Saved DQN visualization to {save_path}")
        else:
            plt.show()
        plt.close()

    def plot_learning_curve(self, save_path=None):
        """Plot the true episodic returns and moving average of loss."""
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axes = plt.subplots(2, 1, figsize=(10, 8))
        
        # Plot True Episode Rewards
        ax = axes[0]
        if len(self.episode_reward_history) > 0:
            ax.plot(self.episode_reward_history, marker='o', markersize=4, alpha=0.4, color='blue', label='Total Episode Return')
            
            # 10-Episode Moving Average
            if len(self.episode_reward_history) >= 10:
                window = 10
                rolling_rewards = np.convolve(self.episode_reward_history, np.ones(window)/window, mode='valid')
                ax.plot(np.arange(window-1, len(self.episode_reward_history)), rolling_rewards, color='darkblue', linewidth=2, label=f'{window}-Ep Moving Avg')
            
            ax.set_title('Episodic Return (Variable Length)')
            ax.set_xlabel('Episodes')
            ax.set_ylabel('Sum of Rewards')
            ax.legend()
        else:
            ax.set_title('Episodic Return (No Episode Data Yet)')

        # Plot Loss (Still step-based, so a standard rolling average works well here)
        ax = axes[1]
        if len(self.loss_history) > 0:
            window = min(100, len(self.loss_history))
            rolling_loss = np.convolve(self.loss_history, np.ones(window)/window, mode='valid')
            ax.plot(np.arange(window-1, len(self.loss_history)), rolling_loss, color='darkred', linewidth=2, label=f'{window}-Step Moving Avg')
            ax.set_title('DQN Step Loss')
            ax.set_xlabel('Training Steps')
            ax.set_ylabel('Loss (MSE)')
            ax.legend()
        else:
            ax.set_title('DQN Loss Curve (No Data)')

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path)
            print(f"Saved learning curve to {save_path}")
        else:
            plt.show()
        plt.close()
        
    def __repr__(self):
        return f"DQNAgent(state_dim={self.state_dim}, n_actions={self.n_actions})"