"""
FedAvg-style averaging of SimArena DQN checkpoints (.pt).

Averages `q_net_state_dict` and `target_net_state_dict` element-wise.
Other fields are taken from the first checkpoint (optimizer, histories, hyperparams).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Union


def _avg_state_dicts(dicts: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not dicts:
        raise ValueError("No state dicts to average")
    keys = dicts[0].keys()
    for d in dicts[1:]:
        if d.keys() != keys:
            raise ValueError("State dict keys differ across checkpoints; cannot FedAvg")
    out: Dict[str, Any] = {}
    for k in keys:
        tensors = [d[k] for d in dicts]
        if hasattr(tensors[0], "dtype"):
            import torch

            out[k] = sum(tensors) / len(tensors)
        else:
            out[k] = tensors[0]
    return out


def fedavg_dqn_checkpoints(local_paths: List[Union[str, Path]]) -> Dict[str, Any]:
    """
    Load multiple DQN .pt checkpoints and return a merged checkpoint dict suitable for torch.save.
    """
    import torch

    paths = [Path(p) for p in local_paths]
    if len(paths) < 1:
        raise ValueError("Need at least one checkpoint path")

    checkpoints: List[Dict[str, Any]] = []
    for p in paths:
        ckpt = torch.load(str(p), map_location="cpu", weights_only=False)
        if "q_net_state_dict" not in ckpt or "target_net_state_dict" not in ckpt:
            raise ValueError(f"Not a DQN checkpoint (missing q/target nets): {p}")
        checkpoints.append(ckpt)

    base = dict(checkpoints[0])
    q_avg = _avg_state_dicts([c["q_net_state_dict"] for c in checkpoints])
    t_avg = _avg_state_dicts([c["target_net_state_dict"] for c in checkpoints])
    base["q_net_state_dict"] = q_avg
    base["target_net_state_dict"] = t_avg
    return base
