import sys
from pathlib import Path

import pytest
import torch
import torch.nn as nn

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.federated_avg import fedavg_dqn_checkpoints


def _fake_dqn_ckpt(weight_fill: float) -> dict:
    q = nn.Linear(4, 3)
    t = nn.Linear(4, 3)
    nn.init.constant_(q.weight, weight_fill)
    nn.init.constant_(q.bias, weight_fill)
    nn.init.constant_(t.weight, weight_fill + 0.1)
    nn.init.constant_(t.bias, weight_fill + 0.1)
    return {
        "q_net_state_dict": q.state_dict(),
        "target_net_state_dict": t.state_dict(),
        "optimizer_state_dict": {},
        "total_steps": 1,
        "reward_history": [],
        "loss_history": [],
        "episode_reward_history": [1.0],
        "current_episode_reward": 1.0,
        "hyperparams": {},
    }


def test_fedavg_two_checkpoints_mean(tmp_path):
    p1 = tmp_path / "a.pt"
    p2 = tmp_path / "b.pt"
    torch.save(_fake_dqn_ckpt(1.0), p1)
    torch.save(_fake_dqn_ckpt(3.0), p2)
    merged = fedavg_dqn_checkpoints([p1, p2])
    assert "q_net_state_dict" in merged
    w = merged["q_net_state_dict"]["weight"]
    assert pytest.approx(float(w.mean()), rel=1e-5) == 2.0


def test_fedavg_single_is_unchanged(tmp_path):
    p = tmp_path / "a.pt"
    torch.save(_fake_dqn_ckpt(5.0), p)
    merged = fedavg_dqn_checkpoints([p])
    w = merged["q_net_state_dict"]["weight"]
    assert pytest.approx(float(w.mean()), rel=1e-5) == 5.0
