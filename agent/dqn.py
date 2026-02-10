import random
import math
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
        """
        Select action using epsilon-greedy policy.
        
        Args:
            state: numpy array or tensor of shape (state_dim,)
        
        Returns:
            action: integer action
        """
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
        """
        Store transition and perform learning update if enough samples.
        
        Args:
            state: current state
            action: action taken
            next_state: next state
            reward: reward received
            done: whether episode terminated
        """
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

    def reset(self):
        """Reset agent (useful for multi-environment training)."""
        # Note: This doesn't reset the network weights, just the step counter
        # If you want to reset everything, create a new agent instance
        pass
    
    def __repr__(self):
        return f"DQNAgent(state_dim={self.state_dim}, n_actions={self.n_actions})"


###############################################################################
# Training function (optional - for backward compatibility)
###############################################################################

def train_dqn(env, agent, num_episodes=500):
    """
    Train DQN agent on environment.
    
    Args:
        env: gym environment
        agent: DQNAgent instance
        num_episodes: number of episodes to train
    
    Returns:
        episode_rewards: list of total rewards per episode
    """
    episode_rewards = []

    for ep in range(num_episodes):
        obs, _ = env.reset()
        state = obs
        
        done = False
        ep_reward = 0

        while not done:
            action = agent.act(state)
            next_obs, reward, done, truncated, _ = env.step(action)
            done = done or truncated
            
            agent.update(state, action, next_obs, reward, done)
            
            state = next_obs
            ep_reward += reward

        episode_rewards.append(ep_reward)
        
        if (ep + 1) % 50 == 0:
            recent_rewards = episode_rewards[-50:]
            avg_reward = sum(recent_rewards) / len(recent_rewards) if recent_rewards else 0.0
            print(f"Episode {ep + 1}/{num_episodes}, Avg Reward (last 50): {avg_reward:.2f}")

    return episode_rewards