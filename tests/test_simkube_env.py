import pytest

gym = pytest.importorskip("gymnasium", reason="gymnasium not installed; skipping SimKube env compliance test")
check_env = pytest.importorskip("gymnasium.utils.env_checker", reason="gymnasium not installed").check_env

# Importing your env module triggers the Gym registration
import env

def test_simkube_env_compliance():
    """
    Tests that the SimKube environment strictly adheres to the 
    standard Gymnasium API contract.
    """
    # 1. Instantiate the environment
    gym_env = gym.make(
        "SimKube-v0",
        initial_trace_path="demo/trace-0001.msgpack",
        namespace="omar",
        deploy="web",
        target=3
    )

    # 2. Run the official environment checker
    # If the environment is broken, this will raise a UserWarning or Exception
    check_env(gym_env.unwrapped)
    
    # Clean up
    gym_env.close()