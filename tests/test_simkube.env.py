import pytest
import gymnasium as gym
from gymnasium.utils.env_checker import check_env

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
        namespace="test-ns",
        deploy="web",
        target=3
    )

    # 2. Run the official environment checker
    # If the environment is broken, this will raise a UserWarning or Exception
    check_env(gym_env.unwrapped)
    
    # Clean up
    gym_env.close()