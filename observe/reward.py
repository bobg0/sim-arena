# observe/reward.py

import functools
from typing import Any, Callable, Dict, Optional
from runner.safeguards import (
    parse_cpu_to_millicores,
    parse_memory_to_bytes,
    MAX_CPU_MILLICORES,
    MAX_MEMORY_BYTES,
    MAX_REPLICAS,
)


def reward_base(obs: dict, target_total: int, T_s: int, resources: dict, **kwargs: Any) -> int:
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


def reward_shaped(obs: dict, target_total: int, T_s: int, resources: dict, **kwargs: Any) -> float:
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

def reward_rui(obs: dict, target_total: int, T_s: int, resources: dict, **kwargs: Any) -> float:

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
        pending_penalty = -0.02 * pending / target_total
        reward += pending_penalty
    
    # 3. Resource waste penalty (too many replicas)
    if total > target_total:
        overshoot = total - target_total
        waste_penalty = -0.07 * overshoot  # Stronger penalty for wasting resources
        reward += waste_penalty
    
    # 4. Under-provisioned penalty (not enough replicas)
    elif total < target_total:
        undershoot = target_total - total
        undershoot_penalty = -0.03 * undershoot / target_total
        reward += undershoot_penalty
    
    # Clamp reward between -1.0 and 1.0
    final_reward = max(-1.0, min(1.0, reward))
    return final_reward

# Reference floor for "minimal reasonable" per-pod; no K8s universal standard exists.
# 500m/256Mi match our action step sizes and align with common K8s doc examples.
REF_CPU_M = 500
REF_MEM_B = 256 * 1024**2


def reward_cost_aware(obs: dict, target_total: int, resources: dict) -> dict:
    """
    Cost-aware reward: computes health, cost, and reward.
    Returns dict with {health, cost, reward, healthy, ...} for tuning/validation.
    """
    ready = int(obs.get("ready", 0))
    pending = int(obs.get("pending", 0))
    total = int(obs.get("total", 0))
    tgt = max(1, int(target_total))

    ready_frac = max(0.0, min(1.0, ready / tgt))
    pending_frac = max(0.0, min(1.0, pending / tgt))
    overshoot_frac = max(0.0, (total - tgt) / tgt)
    undershoot_frac = max(0.0, (tgt - total) / tgt)

    # (#7) Non-linear ready: ready_frac^2 makes last step (2->3) more impactful
    ready_term = ready_frac**2

    # (#5) Overshoot only when healthy: when unhealthy, don't penalize overshoot
    # Stronger pending penalty (0.85): prioritize fixing scheduling (CPU/mem) when pods are pending
    health = (
        1.0 * ready_term
        - 0.85 * pending_frac
        - 0.75 * undershoot_frac
    )

    cpu_per_pod_m = parse_cpu_to_millicores(str(resources.get("cpu", "0m")))
    mem_per_pod_b = parse_memory_to_bytes(str(resources.get("memory", "0Mi")))

    cap_cpu_m = max(REF_CPU_M + 1, int(MAX_CPU_MILLICORES / tgt))
    cap_mem_b = max(REF_MEM_B + 1, int(MAX_MEMORY_BYTES / tgt))

    cpu_excess = max(0, cpu_per_pod_m - REF_CPU_M)
    mem_excess = max(0, mem_per_pod_b - REF_MEM_B)
    cpu_excess_ratio = min(1.0, cpu_excess / (cap_cpu_m - REF_CPU_M)) if cap_cpu_m > REF_CPU_M else 0.0
    mem_excess_ratio = min(1.0, mem_excess / (cap_mem_b - REF_MEM_B)) if cap_mem_b > REF_MEM_B else 0.0
    replica_waste_ratio = min(1.0, max(0.0, overshoot_frac))

    cost = (
        0.45 * cpu_excess_ratio
        + 0.45 * mem_excess_ratio
        + 0.60 * replica_waste_ratio
    )

    healthy = (ready >= tgt) and (pending == 0)
    if healthy:
        reward = 0.9 - 0.6 * cost
    else:
        # Prioritize health when unhealthy: minimal cost weight so agent focuses on fixing scheduling
        cost_weight = 0.08 if pending > 0 else 0.12
        reward = health - cost_weight * cost

    reward = max(-1.0, min(1.0, reward))

    return {
        "health": health,
        "cost": cost,
        "reward": reward,
        "healthy": healthy,
        "ready": ready,
        "pending": pending,
        "total": total,
        "cpu_per_pod_m": cpu_per_pod_m,
        "mem_per_pod_b": mem_per_pod_b,
        "cpu_excess_ratio": cpu_excess_ratio,
        "mem_excess_ratio": mem_excess_ratio,
        "replica_waste_ratio": replica_waste_ratio,
    }


def reward_cost_aware_v2(
    obs: dict,
    target_total: int,
    T_s: int,
    resources: dict,
    *,
    step_idx: int = 0,
    step_penalty: float = 0.0,
    action_info: Optional[dict] = None,
    **kwargs: Any,
) -> float:
    """
    Cost-aware reward: healthy but wasteful penalized.
    (#2) step_penalty: subtract per step to favor faster fixes.
    action_blocked: extra penalty when agent tried an action but it was blocked by safeguards.
    """
    out = reward_cost_aware(obs, target_total, resources)
    r = out["reward"]
    if step_penalty > 0:
        r -= step_penalty
    # Penalty for blocked actions: discourages repeatedly trying invalid actions
    if action_info and action_info.get("blocked", False):
        r -= 0.12
    return max(-1.0, min(1.0, r))


def reward_max_punish(obs: dict, target_total: int, T_s: int, resources: dict, **kwargs: Any) -> float:
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
    "cost_aware_v2": reward_cost_aware_v2,
    "max_punish": reward_max_punish,
    "rui": reward_rui,
}

def get_reward(name: str, **kwargs: Any) -> Callable:
    """
    Get reward function by name. For cost_aware_v2, pass step_penalty via kwargs:
        get_reward("cost_aware_v2", step_penalty=0.01)
    """
    if name not in REWARD_REGISTRY:
        raise ValueError(
            f"Unknown reward '{name}'. Available: {list(REWARD_REGISTRY.keys())}"
        )
    fn = REWARD_REGISTRY[name]
    if kwargs and name == "cost_aware_v2":
        return functools.partial(fn, **kwargs)
    return fn
