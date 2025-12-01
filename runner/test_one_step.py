import types
import builtins
import one_step
# IN THEORY WILL RUN WHEN EVERYTHING IS DONE

# ---- mock external functions ----

one_step.run_hooks = lambda hook, ns: None

one_step.create_simulation = lambda name, trace_path, duration_s, namespace: "sim-123"
one_step.wait_fixed = lambda d: None
one_step.delete_simulation = lambda name, ns: None

one_step.observe = lambda ns, deploy: {
    "ready": 2,
    "pending": 1,
    "total": 3,
}

one_step.compute_reward = lambda obs, target_total, T_s: 1

one_step.apply_action_from_policy = lambda **kwargs: (
    ".tmp/trace-next.msgpack", 
    {"changed": True}
)

# ---- run the test ----

def test_one_step():
    result = one_step.one_step(
        trace_path="demo/trace-0001.msgpack",
        namespace="test-ns",
        deploy="web",
        target=3,
        duration=1,
        seed=0,
    )

    assert result["status"] == 0
    assert result["record"]["obs"]["pending"] == 1
    assert result["record"]["reward"] == 1
    assert result["record"]["action"]["type"] == "bump_cpu_small"