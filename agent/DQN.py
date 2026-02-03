import random
import math
from collections import deque, namedtuple

import numpy as np
import torch
import torch.nn as nn
import torch.optim as optim

# Device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

###############################################################################
# Q-Network
###############################################################################

class QNetwork(nn.Module):
    def __init__(self, state_dim, action_dim):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 24),
            nn.ReLU(),
            nn.Linear(24, 48),
            nn.ReLU(),
            nn.Linear(48, action_dim)
        )

    def forward(self, x):
        return self.net(x.to(device))


###############################################################################
# Epsilon-greedy policy
###############################################################################

def calculate_epsilon(
    step,
    eps_start=1.0,
    eps_end=0.1,
    eps_decay_steps=1000
):
    if step >= eps_decay_steps:
        return eps_end
    return eps_start - (eps_start - eps_end) * (step / eps_decay_steps)


def select_action(state, step, action_dim, q_net):
    epsilon = calculate_epsilon(step)
    if random.random() > epsilon:
        with torch.no_grad():
            return q_net(state).argmax(dim=1).view(1, 1)
    else:
        return torch.tensor([[random.randrange(action_dim)]], device=device)


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
# Training step (DQN + Target Network + Replay)
###############################################################################

def train_step(
    q_net,
    target_net,
    optimizer,
    minibatch,
    gamma=0.99
):
    batch = Transition(*zip(*minibatch))

    state_batch = torch.cat(batch.state)
    action_batch = torch.cat(batch.action)
    reward_batch = torch.cat(batch.reward)
    next_state_batch = torch.cat(batch.next_state)
    done_batch = torch.cat(batch.done)

    # Q(S, A)
    q_values = q_net(state_batch).gather(1, action_batch)

    # Q(S', max_a)
    next_q_values = torch.zeros(len(minibatch), 1, device=device)
    non_terminal_mask = ~done_batch.squeeze()

    if non_terminal_mask.any():
        next_q_values[non_terminal_mask] = (
            target_net(next_state_batch[non_terminal_mask])
            .max(1)[0]
            .unsqueeze(1)
            .detach()
        )

    target = reward_batch.unsqueeze(1) + gamma * next_q_values

    loss = nn.MSELoss()(q_values, target)

    optimizer.zero_grad()
    loss.backward()
    optimizer.step()


###############################################################################
# Main DQN loop
###############################################################################

def DQN(
    env,
    num_episodes=500,
    replay_buffer_size=10000,
    batch_size=32,
    target_update_freq=500,
    gamma=0.99
):
    # Infer state/action space
    obs, _ = env.reset()
    state_dim = obs.shape[0]
    action_dim = env.action_space.n

    q_net = QNetwork(state_dim, action_dim).to(device)
    target_net = QNetwork(state_dim, action_dim).to(device)
    target_net.load_state_dict(q_net.state_dict())
    target_net.eval()

    optimizer = optim.RMSprop(q_net.parameters())
    memory = ReplayMemory(replay_buffer_size)

    total_steps = 0
    episode_rewards = []

    for ep in range(num_episodes):
        obs, _ = env.reset()
        state = torch.tensor(obs, dtype=torch.float32, device=device).unsqueeze(0)

        done = False
        ep_reward = 0

        while not done:
            action = select_action(state, total_steps, action_dim, q_net)

            next_obs, reward, done, _, _ = env.step(action.item())
            next_state = torch.tensor(
                next_obs, dtype=torch.float32, device=device
            ).unsqueeze(0)

            memory.push(
                state,
                action,
                next_state,
                torch.tensor([reward], device=device),
                torch.tensor([done], device=device)
            )

            state = next_state
            ep_reward += reward
            total_steps += 1

            if len(memory) >= batch_size:
                minibatch = memory.sample(batch_size)
                train_step(q_net, target_net, optimizer, minibatch, gamma)

            if total_steps % target_update_freq == 0:
                target_net.load_state_dict(q_net.state_dict())

        episode_rewards.append(ep_reward)

    return episode_rewards
