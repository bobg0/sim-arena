"""Environment module for creating and managing SimKube simulations."""

def _get_env():
    # Import lazily to avoid pulling kubernetes deps during test collection
    from .sim_env import SimEnv  # local import
    return SimEnv()


def create_simulation(name: str, trace_path: str, duration_s: int, namespace: str) -> str:
    """
    Create a Simulation CR and return its name.
    
    This is a wrapper function that matches the signature expected by runner/one_step.py.
    It creates a SimEnv instance, calls create(), and returns the simulation name as a string.
    
    Args:
        name: Kubernetes object name (DNS-1123 compliant)
        trace_path: Path to the trace file (as seen by the driver)
        duration_s: Duration in seconds
        namespace: Target namespace
    
    Returns:
        The simulation name (string)
    """
    env = _get_env()
    handle = env.create(name, trace_path, namespace, duration_s)
    # Return the name as a string (runner expects sim_uid as string)
    return handle.get("name") or name


def wait_fixed(duration_s: int) -> None:
    """
    Wait for a fixed duration.
    
    This is a wrapper function that matches the signature expected by runner/one_step.py.
    
    Args:
        duration_s: Duration in seconds to wait
    """
    env = _get_env()
    env.wait_fixed(duration_s)


def delete_simulation(name: str, namespace: str) -> None:
    """
    Delete a Simulation CR by name and namespace.
    
    This is a wrapper function that matches the signature expected by runner/one_step.py.
    It will try to delete as a simulation first, then fall back to configmap if needed.
    
    Args:
        name: Kubernetes object name
        namespace: Target namespace
    """
    env = _get_env()
    env.delete(name=name, namespace=namespace)

