# observe/test_observe.py
from unittest.mock import patch, Mock

# Import your functions to test
from observe.reward import reward
from observe.reader import observe

# --- 1. Tests for reward.py (doesn't need mock pods) ---

def test_reward_success():
    # Perfect state: ready=3, total=3, pending=0. Target is 3.
    obs = {"ready": 3, "pending": 0, "total": 3}
    assert reward(obs, target_total=3, T_s=120) == 1

def test_reward_fail_pending():
    # Pods are pending
    obs = {"ready": 2, "pending": 1, "total": 3}
    assert reward(obs, target_total=3, T_s=120) == 0

def test_reward_fail_not_ready():
    # A pod is running but not ready (e.g., failing health check)
    obs = {"ready": 2, "pending": 0, "total": 3}
    assert reward(obs, target_total=3, T_s=120) == 0

def test_reward_fail_wrong_total():
    # Scaled to the wrong number
    obs = {"ready": 2, "pending": 0, "total": 2}
    assert reward(obs, target_total=3, T_s=120) == 0

def test_reward_fail_scaled_up_but_not_ready():
    # Agent scaled up, but pods aren't ready yet
    obs = {"ready": 3, "pending": 0, "total": 4}
    assert reward(obs, target_total=3, T_s=120) == 0

# --- 2. Tests for reader.py (Mocks Required) ---

# Helper function to create a mock pod
def create_mock_pod(phase, ready_condition_status):
    pod = Mock()
    pod.status = Mock()
    pod.status.phase = phase
    
    # Mock the condition
    condition = Mock()
    condition.type = "Ready"
    condition.status = ready_condition_status
    pod.status.conditions = [condition]
    return pod

# Use 'patch' to replace the 'v1' client inside the 'reader' module
@patch('observe.reader._ensure_clients')  # Skip client initialization
@patch('observe.reader.v1')
def test_observe_all_ready(mock_v1_client, mock_ensure):
    # 1. Arrange: Create mock return data
    mock_pod_list = Mock()
    mock_pod_list.items = [
        create_mock_pod(phase="Running", ready_condition_status="True"),
        create_mock_pod(phase="Running", ready_condition_status="True")
    ]
    # Configure the mock client's method to return our mock data
    mock_v1_client.list_namespaced_pod.return_value = mock_pod_list
    
    # 2. Act: Call the function
    obs = observe(namespace="test-ns", deployment_name="web")
    
    # 3. Assert
    assert obs == {"ready": 2, "pending": 0, "total": 2}
    # Verify it was called with the correct label selector
    mock_v1_client.list_namespaced_pod.assert_called_with(
        namespace="test-ns", label_selector="app=web"
    )

@patch('observe.reader._ensure_clients')  # Skip client initialization
@patch('observe.reader.v1')
def test_observe_one_pending(mock_v1_client, mock_ensure):
    # 1. Arrange
    mock_pod_list = Mock()
    mock_pod_list.items = [
        create_mock_pod(phase="Running", ready_condition_status="True"),
        create_mock_pod(phase="Pending", ready_condition_status="False") # Pending pod
    ]
    mock_v1_client.list_namespaced_pod.return_value = mock_pod_list
    
    # 2. Act
    obs = observe(namespace="test-ns", deployment_name="web")
    
    # 3. Assert
    assert obs == {"ready": 1, "pending": 1, "total": 2}

# TODO: add more tests for different pod states and error handling
