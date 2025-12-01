from one_step import simple_policy

def test_policy_returns_bump_cpu_when_pending_positive():
    obs = {"pending": 3, "ready": 2, "total": 5}
    result = simple_policy(obs, deploy="web")
    assert result["type"] == "bump_cpu_small"
    assert result["deploy"] == "web"


def test_policy_returns_bump_cpu_when_pending_zero():
    # Note: your code always returns bump_cpu_small even if pending=0
    obs = {"pending": 0}
    result = simple_policy(obs, deploy="api")
    assert result["type"] == "bump_cpu_small"   # matches your current implementation
    assert result["deploy"] == "api"


def test_policy_handles_missing_pending_field():
    obs = {}  # pending defaults to 0
    result = simple_policy(obs, deploy="db")
    assert result["type"] == "bump_cpu_small"
    assert result["deploy"] == "db"
    
    
    
print(simple_policy({"pending": 5}, "web"))
print(simple_policy({"pending": 0}, "web"))
print(simple_policy({}, "web"))