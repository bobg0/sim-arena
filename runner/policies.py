# runner/policies.py
"""
Simple policy plugin registry.

Policies are callables with signature: fn(obs: dict, deploy: str) -> action_dict
"""

import random
from typing import Callable, Dict

def policy_noop(obs: dict, deploy: str):
    return {"type": "noop"}

def policy_heuristic(obs: dict, deploy: str):
    # IMPORTANT # pending because have too much cpu, 
    # bumping cpu will still make pending 
    # probably neeed to reduce cpu for the pending to actually
    # spec: if pending > 0 -> bump_cpu_small(deploy) else noop
    pending = int(obs.get("pending", 0))
    if pending > 0:
        return {"type": "bump_cpu_small", "deploy": deploy}
    return {"type": "noop"}


def policy_random(obs: dict, deploy: str):
    # choose between noop or bump_cpu_small randomly
    if random.random() < 0.5:
        return {"type": "noop"}
    return {"type": "bump_cpu_small", "deploy": deploy}

def policy_always_bump_cpu(obs: dict, deploy: str):
    return {"type": "bump_cpu_small", "deploy": deploy}

def policy_always_bump_mem(obs: dict, deploy: str):
    return {"type": "bump_mem_small", "deploy": deploy}

POLICY_REGISTRY: Dict[str, Callable] = {
    "noop": policy_noop,
    "heuristic": policy_heuristic,
    "random": policy_random,
    "bump_cpu": policy_always_bump_cpu,
    "bump_mem": policy_always_bump_mem,
}

def get_policy(name: str):
    fn = POLICY_REGISTRY.get(name)
    if fn is None:
        raise ValueError(f"Unknown policy '{name}'. Available: {list(POLICY_REGISTRY.keys())}")
    return fn
