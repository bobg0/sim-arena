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

def reward_cost_aware(obs: dict, target_total: int, T_s: int, resources: dict) -> float:
    """
    Cost-aware reward: penalizes over-allocation even when the deployment is healthy.
    
    Teaches the agent to fix problems with minimal resources, not just "any fix works."
    - Success bonus when ready==target, pending==0
    - Cost penalty: higher CPU/memory usage and excess replicas reduce the reward
    - When not healthy: uses shaped-style penalties for distance, pending, etc.
    
    Returns a float between -1.0 and 1.0
    """
    ready = obs.get("ready", 0)
    pending = obs.get("pending", 0)
    total = obs.get("total", 0)
    
    # Perfect health: exactly at target with no pending pods
    if ready == target_total and pending == 0 and total == target_total:
        # Apply cost penalty for over-allocation (total cluster usage)
        cpu_per_pod_m = parse_cpu_to_millicores(str(resources.get("cpu", "0m")))
        mem_per_pod_b = parse_memory_to_bytes(str(resources.get("memory", "0Mi")))
        replicas = int(resources.get("replicas", 0))
        total_cpu_m = cpu_per_pod_m * replicas
        total_mem_b = mem_per_pod_b * replicas
        
        # Normalize to node capacity (16 CPUs, 32 GB)
        cpu_ratio = min(1.0, total_cpu_m / MAX_CPU_MILLICORES)
        mem_ratio = min(1.0, total_mem_b / MAX_MEMORY_BYTES)
        replica_waste = max(0, replicas - target_total)
        
        # Base success reward, minus cost penalties
        cost_penalty = 0.08 * cpu_ratio + 0.08 * mem_ratio + 0.12 * replica_waste
        return max(0.0, 1.0 - cost_penalty)
    
    # Not healthy: use shaped-style penalties
    reward = 0.0
    distance = abs(ready - target_total)
    reward += -0.1 * distance
    if pending > 0:
        reward += -0.05 * pending
    if total > target_total:
        reward += -0.15 * (total - target_total)
    elif total < target_total:
        reward += -0.08 * (target_total - total)
    
    return max(-1.0, min(1.0, reward))


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
    "cost_aware": reward_cost_aware,
    "max_punish": reward_max_punish,
    "rui": reward_rui,
}

def get_reward(name: str):
    if name not in REWARD_REGISTRY:
        raise ValueError(
            f"Unknown reward '{name}'. Available: {list(REWARD_REGISTRY.keys())}"
        )
    return REWARD_REGISTRY[name]
