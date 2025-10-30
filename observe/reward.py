# observe/reward.py

def reward(obs: dict, target_total: int, T_s: int) -> int:
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
