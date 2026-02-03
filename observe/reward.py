# observe/reward.py

from typing import Callable, Dict
from runner.safeguards import (
    parse_cpu_to_millicores,
    parse_memory_to_bytes,
    MAX_CPU_MILLICORES,
    MAX_MEMORY_BYTES,
    MAX_REPLICAS,
)


def reward_base(obs: dict, target_total: int, T_s: int, resources: dict) -> int:
    """
    Calculates a simple binary reward.
    
    Returns 1 if all target pods are present, ready, and none are pending.
    Returns 0 otherwise [discuss this reward structure].
    
    T_s (duration) is unused this week per the spec, but is
    part of the function signature for future use.
    """
    
    # Get values from the observation dict
    ready = obs.get("ready", 0)
    pending = obs.get("pending", 0)
    total = obs.get("total", 0)
    
    # Check for success condition
    if (ready == target_total and 
        total == target_total and 
        pending == 0):
        return 1
    else:
        return 0

def reward_max_punish(obs: dict, target_total: int, T_s: int, resources: dict) -> int:
    """
    Penalize exceeding max resource limits.
    """
    base = reward_base(obs, target_total, T_s, resources)

    cpu_m = parse_cpu_to_millicores(resources["cpu"])
    mem_b = parse_memory_to_bytes(resources["memory"])
    replicas = resources["replicas"]

    penalty = 0

    if cpu_m > MAX_CPU_MILLICORES:
        penalty -= 0.5
    if mem_b > MAX_MEMORY_BYTES:
        penalty -= 0.5
    if replicas > MAX_REPLICAS:
        penalty -= 0.5

    return base + penalty


REWARD_REGISTRY: Dict[str, Callable] = {
    "base": reward_base,
    "max_punish": reward_max_punish,
}

def get_reward(name: str):
    if name not in REWARD_REGISTRY:
        raise ValueError(
            f"Unknown reward '{name}'. Available: {list(REWARD_REGISTRY.keys())}"
        )
    return REWARD_REGISTRY[name]
