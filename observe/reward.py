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


def reward_shaped(obs: dict, target_total: int, T_s: int, resources: dict) -> float:
    """
    Improved reward function with distance-based penalties.
    
    Provides more granular feedback to help agents learn faster:
    - Reward of 1.0 when exactly at target (ready=target, pending=0)
    - Penalties for being away from target (distance-based)
    - Extra penalties for pending pods (inefficiency)
    - Extra penalties for excess replicas (resource waste)
    
    Returns a float between -1.0 and 1.0
    """
    ready = obs.get("ready", 0)
    pending = obs.get("pending", 0)
    total = obs.get("total", 0)
    
    # Perfect: exactly at target with no pending pods
    if ready == target_total and pending == 0 and total == target_total:
        return 1.0
    
    # Calculate penalties
    reward = 0.0
    
    # 1. Distance from target (how far are we from the goal?)
    distance = abs(ready - target_total)
    distance_penalty = -0.1 * distance
    reward += distance_penalty
    
    # 2. Pending pods penalty (inefficiency - pods not ready yet)
    if pending > 0:
        pending_penalty = -0.05 * pending
        reward += pending_penalty
    
    # 3. Resource waste penalty (too many replicas)
    if total > target_total:
        overshoot = total - target_total
        waste_penalty = -0.15 * overshoot  # Stronger penalty for wasting resources
        reward += waste_penalty
    
    # 4. Under-provisioned penalty (not enough replicas)
    elif total < target_total:
        undershoot = target_total - total
        undershoot_penalty = -0.08 * undershoot
        reward += undershoot_penalty
    
    # Clamp reward between -1.0 and 1.0
    final_reward = max(-1.0, min(1.0, reward))
    return final_reward

def reward_rui(obs: dict, target_total: int, T_s: int, resources: dict) -> float:

    ready = obs.get("ready", 0)
    pending = obs.get("pending", 0)
    total = obs.get("total", 0)
    
    # Perfect: exactly at target with no pending pods
    if ready == target_total and pending == 0 and total == target_total:
        return 1.0
    
    # Calculate penalties
    reward = 0.0

    # 2. Pending pods penalty (inefficiency - pods not ready yet)
    if pending > 0:
        pending_penalty = -0.02 * pending
        reward += pending_penalty
    
    # 3. Resource waste penalty (too many replicas)
    if total > target_total:
        overshoot = total - target_total
        waste_penalty = -0.07 * overshoot  # Stronger penalty for wasting resources
        reward += waste_penalty
    
    # 4. Under-provisioned penalty (not enough replicas)
    elif total < target_total:
        undershoot = target_total - total
        undershoot_penalty = -0.03 * undershoot
        reward += undershoot_penalty
    
    # Clamp reward between -1.0 and 1.0
    final_reward = max(-1.0, min(1.0, reward))
    return final_reward

def reward_max_punish(obs: dict, target_total: int, T_s: int, resources: dict) -> float:
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
    "shaped": reward_shaped,
    "max_punish": reward_max_punish,
    "rui": reward_rui,
}

def get_reward(name: str):
    if name not in REWARD_REGISTRY:
        raise ValueError(
            f"Unknown reward '{name}'. Available: {list(REWARD_REGISTRY.keys())}"
        )
    return REWARD_REGISTRY[name]
