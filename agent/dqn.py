import random
import math
import os
from collections import deque, namedtuple

import torch
import torch.nn as nn
import torch.optim as optim

from .agent import BaseAgent, ACTION_NAMES


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

    def reset(self, reset_steps=True):
        """Reset agent (useful for multi-environment training or transfer learning)."""
        self.reward_history = []
        self.loss_history = []
        self.episode_reward_history = []
        self.current_episode_reward = 0.0
        
        # ADD THIS: Reset total steps to restart epsilon decay for the new environment
        if reset_steps:
            self.total_steps = 0
    
    def visualize(self, save_path=None):
        """Visualize DQN: Q-value heatmaps, action bar chart, and epsilon decay."""
        import matplotlib.pyplot as plt
        import numpy as np

        # Define configurations for the 4 subplots (Low/High CPU and Low/High Mem)
        configs = [
            {"title": "Low CPU / Low Mem", "cpu": 500, "mem": 512},
            {"title": "High CPU / Low Mem", "cpu": 1500, "mem": 512},
            {"title": "Low CPU / High Mem", "cpu": 500, "mem": 1024},
            {"title": "High CPU / High Mem", "cpu": 1500, "mem": 1024}
        ]

        pending = 0
        distance_sweep = list(range(5))  # Sweeps distances 0 through 4
        # replicas/8: 0.125 for 1, 0.25 for 2, 0.375 for 3 (target)
        replicas_norm = 0.375  # target=3

        action_labels = ACTION_NAMES[:self.n_actions] if self.n_actions <= len(ACTION_NAMES) else [f"A{i}" for i in range(self.n_actions)]

        # Set to eval mode for visualization
        self.q_net.eval()

        # --- STEP 1: Pre-compute all Q-values to find global min and max ---
        all_q_values = []
        global_min = float('inf')
        global_max = float('-inf')

        for config in configs:
            states = []
            for d in distance_sweep:
                states.append([config["cpu"] / 4000, config["mem"] / 4096, pending / 5, d / 5, replicas_norm])
                
            states_tensor = torch.tensor(states, dtype=torch.float32, device=self.device)
            
            with torch.no_grad():
                q_values = self.q_net(states_tensor).cpu()
                
            all_q_values.append(q_values)
            global_min = min(global_min, torch.min(q_values).item())
            global_max = max(global_max, torch.max(q_values).item())

        # Determine threshold for text color (black vs white) based on global scale
        if global_max == global_min:
            threshold = global_max
        else:
            threshold = (global_max + global_min) / 2

        # Layout: 2x2 heatmaps, bar chart, epsilon (4 rows)
        fig = plt.figure(figsize=(14, 14))
        gs = fig.add_gridspec(4, 2, height_ratios=[1, 1, 0.6, 0.5], hspace=0.4, wspace=0.3)
        fig.suptitle('DQN Agent Visualization', fontsize=16)

        im = None
        for idx, (config, q_values) in enumerate(zip(configs, all_q_values)):
            ax = fig.add_subplot(gs[idx // 2, idx % 2])
            im = ax.imshow(q_values, aspect='auto', cmap='viridis', vmin=global_min, vmax=global_max)
            ax.set_xticks(range(self.n_actions))
            ax.set_xticklabels(action_labels, rotation=45, ha='right')
            ax.set_yticks(range(len(distance_sweep)))
            ax.set_yticklabels([f"Dist={r}" for r in distance_sweep])
            for i in range(len(distance_sweep)):
                for j in range(self.n_actions):
                    val = q_values[i, j].item()
                    color = "black" if val > threshold else "white"
                    ax.text(j, i, f"{val:.2f}", ha="center", va="center", color=color)
            ax.set_xlabel('Action')
            ax.set_ylabel('Distance to target')
            ax.set_title(f"{config['title']}\n(CPU: {config['cpu']}m / Mem: {config['mem']}Mi)")

        # Row 2: Q-value bar chart for typical state (distance=2, mid CPU/mem)
        typical_state = [1000 / 4000, 768 / 4096, 0, 2 / 5, replicas_norm]  # distance=2
        with torch.no_grad():
            typical_tensor = torch.tensor([typical_state], dtype=torch.float32, device=self.device)
            typical_q = self.q_net(typical_tensor).cpu().numpy().flatten()
        ax_bar = fig.add_subplot(gs[2, :])
        colors = ['#2ecc71' if i == np.argmax(typical_q) else '#3498db' for i in range(self.n_actions)]
        ax_bar.bar(range(self.n_actions), typical_q, color=colors, edgecolor='black')
        ax_bar.set_xticks(range(self.n_actions))
        ax_bar.set_xticklabels(action_labels, rotation=45, ha='right')
        ax_bar.set_ylabel('Q-Value')
        ax_bar.set_title('Q-Values for Typical State (CPU: 1000m, Mem: 768Mi, Distance: 2) — best action in green')
        ax_bar.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
        ax_bar.grid(axis='y', alpha=0.3)

        # Row 3: Epsilon decay over training
        ax_eps = fig.add_subplot(gs[3, :])
        steps_range = np.arange(0, max(self.total_steps + 100, self.eps_decay_steps + 100))
        eps_vals = np.where(steps_range >= self.eps_decay_steps, self.eps_end,
                            self.eps_start - (self.eps_start - self.eps_end) * (steps_range / self.eps_decay_steps))
        ax_eps.plot(steps_range, eps_vals, color='purple', alpha=0.8, label='Epsilon schedule')
        ax_eps.axvline(x=self.total_steps, color='red', linestyle='--', alpha=0.7, label=f'Current step ({self.total_steps})')
        ax_eps.axvline(x=self.eps_decay_steps, color='orange', linestyle=':', alpha=0.7, label=f'Decay end ({self.eps_decay_steps})')
        ax_eps.set_xlabel('Training Steps')
        ax_eps.set_ylabel('Epsilon')
        ax_eps.set_title('Exploration vs Exploitation (epsilon-greedy)')
        ax_eps.legend(loc='upper right', fontsize=8)
        ax_eps.set_xlim(0, max(self.total_steps, self.eps_decay_steps) + 50)
        ax_eps.grid(alpha=0.3)

        # Colorbar for heatmaps
        cbar_ax = fig.add_axes([0.92, 0.42, 0.02, 0.45])
        fig.colorbar(im, cax=cbar_ax, label='Q-Value')

        self.q_net.train()

        if save_path:
            plt.savefig(save_path)
            print(f"Saved DQN visualization to {save_path}")
        else:
            plt.show()
        plt.close()

    def plot_learning_curve(self, save_path=None):
        """Plot episodic returns, step rewards, and loss."""
        import matplotlib.pyplot as plt
        import numpy as np

        fig, axes = plt.subplots(3, 1, figsize=(10, 10))
        
        # Plot 1: Episode returns
        ax = axes[0]
        if len(self.episode_reward_history) > 0:
            ax.plot(self.episode_reward_history, marker='o', markersize=4, alpha=0.4, color='blue', label='Total Episode Return')
            if len(self.episode_reward_history) >= 10:
                window = 10
                rolling_rewards = np.convolve(self.episode_reward_history, np.ones(window)/window, mode='valid')
                ax.plot(np.arange(window-1, len(self.episode_reward_history)), rolling_rewards, color='darkblue', linewidth=2, label=f'{window}-Ep Moving Avg')
            ax.set_title('Episodic Return (Sum of Rewards per Episode)')
            ax.set_xlabel('Episodes')
            ax.set_ylabel('Return')
            ax.legend()
        else:
            ax.set_title('Episodic Return (No Episode Data Yet)')
        ax.grid(alpha=0.3)

        # Plot 2: Step rewards (per-step feedback)
        ax = axes[1]
        if len(self.reward_history) > 0:
            window = min(100, len(self.reward_history))
            rolling = np.convolve(self.reward_history, np.ones(window)/window, mode='valid')
            ax.plot(self.reward_history, alpha=0.3, color='green', label='Step Reward')
            ax.plot(np.arange(window-1, len(self.reward_history)), rolling, color='darkgreen', linewidth=2, label=f'{window}-Step Moving Avg')
            ax.set_title('Step Rewards (Per-Step Feedback)')
            ax.set_xlabel('Training Steps')
            ax.set_ylabel('Reward')
            ax.legend()
        else:
            ax.set_title('Step Rewards (No Data Yet)')
        ax.grid(alpha=0.3)

        # Plot 3: Loss
        ax = axes[2]
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
        ax.grid(alpha=0.3)

        plt.tight_layout()
        if save_path:
            plt.savefig(save_path)
            print(f"Saved learning curve to {save_path}")
        else:
            plt.show()
        plt.close()
        
    def __repr__(self):
        return f"DQNAgent(state_dim={self.state_dim}, n_actions={self.n_actions})"