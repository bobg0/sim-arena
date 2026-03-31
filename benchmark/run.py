"""
benchmark/run.py

Entry point for benchmarking an LLM (Gemini or Anthropic Claude) against
the Sim-Arena Kubernetes resource-optimisation scenarios.

Usage examples
--------------
  # Gemini (default model: gemini-2.5-flash-lite)
  python benchmark/run.py --provider gemini --ns virtual-default

  # Gemini with a specific model
  python benchmark/run.py --provider gemini --model gemini-2.5-pro --ns virtual-default

  # Anthropic Claude
  python benchmark/run.py --provider anthropic --model claude-sonnet-4-20250514 --ns virtual-default

  # Single problem type
  python benchmark/run.py --provider gemini --filter-type replica-tiny-scale

  # Dry-run: list scenarios without running
  python benchmark/run.py --list-scenarios
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Load .env early so provider constructors can read API keys
from dotenv import load_dotenv
load_dotenv()

_script_dir   = Path(__file__).parent.absolute()
_project_root = _script_dir.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from agent.agent import Agent, AgentType
from agent.providers import make_provider
from benchmark.scenarios import load_scenarios
from benchmark.metrics import BenchmarkMetrics, EpisodeMetrics, make_step_record
from sim_mcp.client import MCPClientSync
from runner.multi_step import run_episode

logger = logging.getLogger("benchmark.run")

ACTION_SPACE = {
    0: "noop",
    1: "bump_cpu_small",
    2: "bump_mem_small",
    3: "scale_up_replicas",
    4: "reduce_cpu_small",
    5: "reduce_mem_small",
    6: "scale_down_replicas",
}


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Benchmark an LLM on Sim-Arena K8s scenarios."
    )

    # Provider selection
    parser.add_argument("--provider", type=str, default="gemini",
                        choices=["gemini", "anthropic"],
                        help="LLM provider to benchmark (default: gemini)")
    parser.add_argument("--model", type=str, default=None,
                        help="Model override. Defaults: gemini=gemini-2.0-flash, "
                             "anthropic=claude-sonnet-4-20250514")
    parser.add_argument("--max-tool-rounds", type=int, default=8,
                        help="Max MCP tool-call rounds per step (default: 8)")

    # Namespace / environment
    parser.add_argument("--ns", "--namespace", dest="namespace",
                        default="virtual-default",
                        help="Kubernetes namespace (default: virtual-default)")
    parser.add_argument("--deploy", type=str, default="web",
                        help="Deployment name (default: web)")

    # Scenario selection
    parser.add_argument("--filter-type", type=str, default=None,
                        help="Only run scenarios of this problem_type")
    parser.add_argument("--scenario", type=str, default=None,
                        help="Run a single scenario by name")
    parser.add_argument("--list-scenarios", action="store_true",
                        help="Print available scenarios and exit")

    # Simulation parameters
    parser.add_argument("--duration", type=int, default=60,
                        help="Seconds per simulation step (default: 60)")
    parser.add_argument("--steps", type=int, default=10,
                        help="Max steps per episode (default: 10)")
    parser.add_argument("--reward", type=str, default="shaped",
                        help="Reward function: base/shaped/cost_aware_v2/max_punish "
                             "(default: shaped)")
    parser.add_argument("--seed", type=int, default=42)

    # Output
    parser.add_argument("--results-dir", type=str, default=None,
                        help="Override output directory")
    parser.add_argument("--log-level", type=str, default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])

    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper()),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    # ---- scenario loading -------------------------------------------------
    scenarios = load_scenarios(filter_type=args.filter_type)
    if args.scenario:
        scenarios = [s for s in scenarios if s["name"] == args.scenario]
        if not scenarios:
            logger.error(f"No scenario named '{args.scenario}'.")
            return 1

    if args.list_scenarios:
        print(f"\nAvailable scenarios ({len(scenarios)}):\n")
        for s in scenarios:
            print(f"  {s['name']:<35} type={s['problem_type']:<20} target={s['target']}")
        print()
        return 0

    if not scenarios:
        logger.error("No scenarios matched the given filters.")
        return 1

    # ---- provider setup ---------------------------------------------------
    try:
        provider = make_provider(args.provider, model=args.model)
    except EnvironmentError as exc:
        logger.error(str(exc))
        return 1

    model_label = provider.model_name

    # ---- output directory ------------------------------------------------
    timestamp   = datetime.now().strftime("%Y%m%d_%H%M%S")
    results_dir = Path(args.results_dir) if args.results_dir else (
        _project_root / "benchmark" / "results"
        / f"{timestamp}_{args.provider}_{model_label.replace('/', '-')}"
    )
    results_dir.mkdir(parents=True, exist_ok=True)

    with open(results_dir / "command.txt", "w") as f:
        f.write(" ".join(sys.argv) + "\n\n")
        for k, v in vars(args).items():
            f.write(f"{k}: {v}\n")

    logger.info("=" * 60)
    logger.info("Benchmark start")
    logger.info(f"  provider  : {args.provider}")
    logger.info(f"  model     : {model_label}")
    logger.info(f"  scenarios : {len(scenarios)}")
    logger.info(f"  steps/ep  : {args.steps}  duration: {args.duration}s")
    logger.info(f"  results   : {results_dir}")
    logger.info("=" * 60)

    # ---- benchmark loop --------------------------------------------------
    bm_metrics = BenchmarkMetrics(model=model_label)

    with MCPClientSync() as mcp_client:
        agent = Agent(
            AgentType.LLM,
            provider        = provider,
            mcp_client      = mcp_client,
            max_tool_rounds = args.max_tool_rounds,
        )

        for i, scenario in enumerate(scenarios, 1):
            logger.info(
                f"\n[{i}/{len(scenarios)}] {scenario['name']} "
                f"(type={scenario['problem_type']}, target={scenario['target']})"
            )

            trace_path = str(_project_root / scenario["trace"])
            ep_metrics = EpisodeMetrics(scenario=scenario)
            ep_seed    = args.seed + i * 1000

            # Inject scenario name for richer prompts
            agent._agent.scenario_name = scenario["name"]

            try:
                result = run_episode(
                    trace_path      = trace_path,
                    namespace       = args.namespace,
                    deploy          = args.deploy,
                    target          = scenario["target"],
                    duration        = args.duration,
                    steps           = args.steps,
                    seed            = ep_seed,
                    agent_name      = "llm",
                    reward_name     = args.reward,
                    agent           = agent,
                    reward_kwargs   = None,
                    obs_noise_scale = 0.0,
                    min_return      = None,
                    state_space     = "base",
                    updates_per_step= 1,   # no gradient updates for LLM
                )
            except Exception as exc:
                logger.error(f"Episode failed for '{scenario['name']}': {exc}")
                ep_metrics.close()
                bm_metrics.add_episode(ep_metrics)
                continue

            ep_metrics.close()

            for record in result.get("records", []):
                obs        = record.get("obs", {})
                action_idx = record.get("action_idx") or 0
                reward     = record.get("reward", 0.0)
                at_target  = record.get("at_target", False)
                step_idx   = record.get("step_idx", len(ep_metrics.step_records))

                # Match LLM metadata from agent's step_records by position
                llm_meta = {}
                if agent._agent.step_records:
                    idx = len(ep_metrics.step_records)
                    if idx < len(agent._agent.step_records):
                        llm_meta = agent._agent.step_records[idx]

                ep_metrics.record_step(make_step_record(
                    episode_name = scenario["name"],
                    step_idx     = step_idx,
                    obs          = obs,
                    action_idx   = action_idx,
                    action_type  = ACTION_SPACE.get(action_idx, "unknown"),
                    reward       = reward,
                    tool_calls   = llm_meta.get("tool_calls", []),
                    latency_s    = llm_meta.get("latency_s", 0.0),
                    at_target    = at_target,
                    reasoning    = llm_meta.get("reasoning", ""),
                ))

            bm_metrics.add_episode(ep_metrics)
            summary = ep_metrics.summarise()
            logger.info(
                f"  → solved={summary['solved']}  "
                f"steps={summary['steps_executed']}  "
                f"reward={summary['total_reward']}  "
                f"tool_calls={summary['total_tool_calls']}"
            )

    # ---- save results ----------------------------------------------------
    report = bm_metrics.save(results_dir=results_dir, also_markdown=True)

    logger.info("\n" + "=" * 60)
    logger.info("Benchmark complete")
    logger.info(f"  solved    : {report['n_solved']}/{report['n_scenarios']} "
                f"({report['solve_rate']*100:.1f}%)")
    logger.info(f"  avg reward: {report['avg_total_reward']}")
    logger.info(f"  results   : {results_dir}")
    logger.info("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
