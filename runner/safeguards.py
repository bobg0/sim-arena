# runner/safeguards.py
"""
Safeguard/validation logic to prevent absurd resource allocations.

This module provides validation functions to ensure actions don't exceed 
reasonable limits (e.g., max CPU, max memory, max replicas).
"""

from typing import Tuple, Optional

# Configurable limits
MAX_CPU_MILLICORES = 16000  # 16 CPUs
MAX_MEMORY_BYTES = 34359738368  # 32 GB
MAX_REPLICAS = 100

# CPU conversion helpers
def parse_cpu_to_millicores(cpu_str: str) -> int:
    """Convert CPU string (e.g., '500m', '2', '1.5') to millicores."""
    cpu_str = cpu_str.strip()
    if cpu_str.endswith('m'):
        return int(cpu_str[:-1])
    else:
        return int(float(cpu_str) * 1000)

def parse_memory_to_bytes(mem_str: str) -> int:
    """Convert memory string (e.g., '256Mi', '1Gi') to bytes."""
    mem_str = mem_str.strip()
    units = {
        'Ki': 1024,
        'Mi': 1024**2,
        'Gi': 1024**3,
        'Ti': 1024**4,
        'K': 1000,
        'M': 1000**2,
        'G': 1000**3,
        'T': 1000**4,
    }
    
    for unit, factor in units.items():
        if mem_str.endswith(unit):
            return int(float(mem_str[:-len(unit)]) * factor)
    
    # No unit means bytes
    return int(mem_str)

def validate_cpu_action(current_cpu: str, step: str, action_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a CPU action won't exceed limits.
    
    Returns: (is_valid, error_message)
    """
    try:
        current_millicores = parse_cpu_to_millicores(current_cpu) if current_cpu else 0
        step_millicores = parse_cpu_to_millicores(step)
        
        if action_type == "bump_cpu_small":
            new_millicores = current_millicores + step_millicores
        else:
            new_millicores = current_millicores
        
        if new_millicores > MAX_CPU_MILLICORES:
            return False, f"CPU would exceed limit: {new_millicores}m > {MAX_CPU_MILLICORES}m (16 CPUs)"
        
        return True, None
    except Exception as e:
        return False, f"Failed to parse CPU values: {e}"

def validate_memory_action(current_memory: str, step: str, action_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a memory action won't exceed limits.
    
    Returns: (is_valid, error_message)
    """
    try:
        current_bytes = parse_memory_to_bytes(current_memory) if current_memory else 0
        step_bytes = parse_memory_to_bytes(step)
        
        if action_type == "bump_mem_small":
            new_bytes = current_bytes + step_bytes
        else:
            new_bytes = current_bytes
        
        if new_bytes > MAX_MEMORY_BYTES:
            return False, f"Memory would exceed limit: {new_bytes} bytes > {MAX_MEMORY_BYTES} bytes (32Gi)"
        
        return True, None
    except Exception as e:
        return False, f"Failed to parse memory values: {e}"

def validate_replicas_action(current_replicas: int, delta: int, action_type: str) -> Tuple[bool, Optional[str]]:
    """
    Validate that a replica action won't exceed limits.
    
    Returns: (is_valid, error_message)
    """
    if action_type == "scale_up_replicas":
        new_replicas = current_replicas + delta
    else:
        new_replicas = current_replicas
    
    if new_replicas > MAX_REPLICAS:
        return False, f"Replicas would exceed limit: {new_replicas} > {MAX_REPLICAS}"
    
    return True, None

def validate_action(action: dict, current_state: Optional[dict] = None) -> Tuple[bool, Optional[str]]:
    """
    Main validation function for any action.
    
    Args:
        action: Action dict with 'type' and parameters
        current_state: Optional dict with current resource values
        
    Returns: (is_valid, error_message)
    """
    action_type = action.get("type", "noop")
    
    if action_type == "noop":
        return True, None
    
    # For now, we validate based on action parameters
    # In the future, we could load current values from the trace
    if action_type == "bump_cpu_small":
        # Get current from state or assume 0
        current_cpu = current_state.get("cpu", "0m") if current_state else "0m"
        step = action.get("step", "500m")
        return validate_cpu_action(current_cpu, step, action_type)
    
    elif action_type == "bump_mem_small":
        current_memory = current_state.get("memory", "0Mi") if current_state else "0Mi"
        step = action.get("step", "256Mi")
        return validate_memory_action(current_memory, step, action_type)
    
    elif action_type == "scale_up_replicas":
        current_replicas = current_state.get("replicas", 0) if current_state else 0
        delta = action.get("delta", 1)
        return validate_replicas_action(current_replicas, delta, action_type)
    
    # Unknown action type - let it through (will fail elsewhere)
    return True, None
