"""
benchmark/metrics.py

Metric collection and aggregation for the LLM benchmark.

Collects:
  Per step:   action taken, reward, tool calls made, latency, solved
  Per episode: steps_to_solve, total_reward, solved, tool_call_distribution

Aggregates:
  Per scenario / per problem_type / overall summary

All data is stored as plain dicts so it can be serialised directly to JSON.
"""

from __future__ import annotations

import json
import time
from collections import defaultdict
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# Step-level record
# ---------------------------------------------------------------------------

def make_step_record(
    episode_name:  str,
    step_idx:      int,
    obs:           dict,
    action_idx:    int,
    action_type:   str,
    reward:        float,
    tool_calls:    list[str],
    latency_s:     float,
    at_target:     bool,
    reasoning:     str = "",
) -> dict:
    return {
        "episode_name": episode_name,
        "step_idx":     step_idx,
        "obs":          obs,
        "action_idx":   action_idx,
        "action_type":  action_type,
        "reward":       reward,
        "tool_calls":   tool_calls,
        "n_tool_calls": len(tool_calls),
        "latency_s":    latency_s,
        "at_target":    at_target,
        "reasoning":    reasoning,
    }


# ---------------------------------------------------------------------------
# Episode-level aggregator
# ---------------------------------------------------------------------------

class EpisodeMetrics:
    """
    Aggregates step records for a single episode (one scenario run).
    """

    def __init__(self, scenario: dict) -> None:
        self.scenario      = scenario           # from scenarios/index.json
        self.step_records: list[dict] = []
        self.start_time    = time.time()
        self.end_time:     float | None = None

    def record_step(self, record: dict) -> None:
        self.step_records.append(record)

    def close(self) -> None:
        self.end_time = time.time()

    def summarise(self) -> dict:
        """Return a summary dict for this episode."""
        solved           = any(r["at_target"] for r in self.step_records)
        steps_to_solve   = next(
            (r["step_idx"] + 1 for r in self.step_records if r["at_target"]),
            None,
        )
        total_reward     = sum(r["reward"] for r in self.step_records)
        total_tool_calls = sum(r["n_tool_calls"] for r in self.step_records)
        total_latency    = sum(r["latency_s"] for r in self.step_records)

        # Action distribution
        action_counts: dict[int, int] = defaultdict(int)
        for r in self.step_records:
            action_counts[r["action_idx"]] += 1

        # Tool call distribution
        tool_counts: dict[str, int] = defaultdict(int)
        for r in self.step_records:
            for t in r["tool_calls"]:
                tool_counts[t] += 1

        return {
            "scenario_name":      self.scenario["name"],
            "problem_type":       self.scenario["problem_type"],
            "trace":              self.scenario["trace"],
            "target":             self.scenario["target"],
            "solved":             solved,
            "steps_executed":     len(self.step_records),
            "steps_to_solve":     steps_to_solve,
            "total_reward":       round(total_reward, 4),
            "total_tool_calls":   total_tool_calls,
            "avg_tool_calls_per_step": round(
                total_tool_calls / max(len(self.step_records), 1), 2
            ),
            "total_latency_s":    round(total_latency, 2),
            "avg_latency_per_step_s": round(
                total_latency / max(len(self.step_records), 1), 3
            ),
            "action_distribution": dict(action_counts),
            "tool_distribution":   dict(tool_counts),
            "elapsed_s":          round(
                (self.end_time or time.time()) - self.start_time, 2
            ),
        }


# ---------------------------------------------------------------------------
# Run-level aggregator
# ---------------------------------------------------------------------------

class BenchmarkMetrics:
    """
    Collects EpisodeMetrics for a full benchmark run and produces
    an aggregated report.
    """

    def __init__(self, model: str) -> None:
        self.model    = model
        self.episodes: list[EpisodeMetrics] = []
        self.run_start = time.time()

    def add_episode(self, ep: EpisodeMetrics) -> None:
        self.episodes.append(ep)

    def aggregate(self) -> dict:
        """Produce a full benchmark report dict."""
        summaries = [ep.summarise() for ep in self.episodes]

        # ---- overall -------------------------------------------------------
        n          = len(summaries)
        n_solved   = sum(1 for s in summaries if s["solved"])
        solve_rate = round(n_solved / max(n, 1), 4)

        avg_reward      = _mean([s["total_reward"]        for s in summaries])
        avg_steps       = _mean([s["steps_executed"]       for s in summaries])
        avg_tool_calls  = _mean([s["total_tool_calls"]     for s in summaries])
        avg_latency     = _mean([s["total_latency_s"]      for s in summaries])

        steps_to_solve_vals = [
            s["steps_to_solve"] for s in summaries
            if s["steps_to_solve"] is not None
        ]
        avg_steps_to_solve = _mean(steps_to_solve_vals) if steps_to_solve_vals else None

        # ---- per problem_type ----------------------------------------------
        by_type: dict[str, list[dict]] = defaultdict(list)
        for s in summaries:
            by_type[s["problem_type"]].append(s)

        per_type_stats = {}
        for ptype, group in by_type.items():
            per_type_stats[ptype] = {
                "n":          len(group),
                "solve_rate": round(sum(1 for s in group if s["solved"]) / len(group), 4),
                "avg_reward": _mean([s["total_reward"] for s in group]),
                "avg_steps":  _mean([s["steps_executed"] for s in group]),
            }

        return {
            "model":               self.model,
            "total_elapsed_s":     round(time.time() - self.run_start, 2),
            "n_scenarios":         n,
            "n_solved":            n_solved,
            "solve_rate":          solve_rate,
            "avg_total_reward":    avg_reward,
            "avg_steps_executed":  avg_steps,
            "avg_steps_to_solve":  avg_steps_to_solve,
            "avg_tool_calls":      avg_tool_calls,
            "avg_latency_s":       avg_latency,
            "per_problem_type":    per_type_stats,
            "episodes":            summaries,
        }

    def save(self, results_dir: str | Path, also_markdown: bool = True) -> None:
        """Write report.json (and optionally report.md) to results_dir."""
        results_dir = Path(results_dir)
        results_dir.mkdir(parents=True, exist_ok=True)

        report = self.aggregate()

        json_path = results_dir / "report.json"
        with open(json_path, "w") as f:
            json.dump(report, f, indent=2)

        if also_markdown:
            md_path = results_dir / "report.md"
            with open(md_path, "w") as f:
                f.write(_render_markdown(report))

        return report


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mean(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 4)


def _render_markdown(report: dict) -> str:
    lines = [
        f"# Benchmark Report",
        f"",
        f"**Model**: {report['model']}",
        f"**Scenarios**: {report['n_scenarios']}  "
        f"| **Solved**: {report['n_solved']} ({report['solve_rate']*100:.1f}%)",
        f"**Avg reward**: {report['avg_total_reward']}  "
        f"| **Avg steps**: {report['avg_steps_executed']}  "
        f"| **Avg steps to solve**: {report['avg_steps_to_solve']}",
        f"**Avg tool calls/episode**: {report['avg_tool_calls']}  "
        f"| **Avg latency/episode**: {report['avg_latency_s']}s",
        f"",
        f"## Results by Problem Type",
        f"",
        f"| Type | N | Solve Rate | Avg Reward | Avg Steps |",
        f"|------|---|-----------|------------|-----------|",
    ]
    for ptype, stats in report["per_problem_type"].items():
        lines.append(
            f"| {ptype} | {stats['n']} | {stats['solve_rate']*100:.1f}% "
            f"| {stats['avg_reward']} | {stats['avg_steps']} |"
        )

    lines += [
        f"",
        f"## Per-Scenario Results",
        f"",
        f"| Scenario | Type | Solved | Steps | Reward | Tool Calls |",
        f"|----------|------|--------|-------|--------|------------|",
    ]
    for ep in report["episodes"]:
        solved_str = "✅" if ep["solved"] else "❌"
        lines.append(
            f"| {ep['scenario_name']} | {ep['problem_type']} | {solved_str} "
            f"| {ep['steps_executed']} | {ep['total_reward']} "
            f"| {ep['total_tool_calls']} |"
        )

    return "\n".join(lines) + "\n"
