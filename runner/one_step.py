"""
runner/one_step.py

Orchestrate one reproducible agent step:
pre_start hook -> create_simulation -> wait_fixed -> observe -> policy -> edit trace -> save trace -> reward -> log

Usage:
  python runner/one_step.py --trace demo/trace-0001.msgpack --ns test-ns --deploy web --target 3 --duration 120
"""
# ---- Try importing project modules (fail fast with helpful message) ----
try:
    from ops.hooks import run_hooks
except Exception as e:
    print("ERROR: failed to import ops.hooks.run_hooks. Make sure /ops is on PYTHONPATH and file exists.", file=sys.stderr)
    raise

try:
    from env.sim_env import create_simulation, wait_fixed, delete_simulation
except Exception as e:
    print("ERROR: failed to import env.sim_env functions. Make sure /env/sim_env.py exists.", file=sys.stderr)
    raise

try:
    from observe.reader import observe
    from observe.reward import reward as compute_reward
except Exception as e:
    print("ERROR: failed to import observe.reader or observe.reward. Make sure /observe exists.", file=sys.stderr)
    raise

try:
    from actions.trace_io import load_trace, save_trace
    from actions.ops import bump_cpu_small
except Exception as e:
    print("ERROR: failed to import actions.trace_io or actions.ops. Make sure /actions exists.", file=sys.stderr)
    raise

# ---- Logging setup ----
LOG_DIR = Path("runs")
LOG_DIR.mkdir(parents=True, exist_ok=True)
STEP_LOG = LOG_DIR / "step.jsonl"
SUMMARY_LOG = LOG_DIR / "summary.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("one_step")

# ---- Policy (heuristic) ----
def simple_policy(obs: dict, deploy: str):
    """
    Heuristic policy:
      - if pending > 0: request bump_cpu_small
      - else: noop
    Returns: dict describing action: {"type": "bump_cpu_small", "deploy": deploy} or {"type": "noop"}
    """
    pending = int(obs.get("pending", 0))
    if pending > 0:
        return {"type": "bump_cpu_small", "deploy": deploy}
    return {"type": "noop"}