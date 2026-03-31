"""
agent/llm_agent.py

LLMAgent: provider-agnostic agent that fixes Kubernetes resource problems
by calling MCP tools to inspect the live cluster before choosing an action.

The actual API call and tool-use loop is handled by the injected LLMProvider
(AnthropicProvider or GeminiProvider). This class manages:
  - Prompt construction (via prompt_builder)
  - Dispatching to the provider
  - Step / episode metric recording
  - save() / load() of run metadata

Interface (same as DQN/EpsGreedy for runner/one_step.py compatibility):

    agent.act(obs, namespace, deploy, step_idx, max_steps, scenario_name) → int
    agent.update(...)  → no-op
    agent.save(path)   → JSON metadata
    agent.load(path)   → restore metadata
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

# Load .env before anything that reads env vars (providers, API clients)
from sim_mcp.client import MCPClientSync  # noqa: F401 — re-exported for callers

from dotenv import load_dotenv
load_dotenv()

from agent.providers.base import LLMProvider
from agent.prompt_builder import build_system_prompt, build_user_message

logger = logging.getLogger("llm_agent")

MAX_TOOL_ROUNDS = 8


class LLMAgent:
    """
    Provider-agnostic LLM agent with MCP-backed Kubernetes tool use.

    Args:
        provider:        An LLMProvider instance (AnthropicProvider or GeminiProvider).
        mcp_client:      MCPClientSync instance that has already been started.
        max_tool_rounds: Hard cap on tool-call rounds per act() call.
    """

    def __init__(
        self,
        provider:        LLMProvider,
        mcp_client,                          # MCPClientSync
        max_tool_rounds: int = MAX_TOOL_ROUNDS,
    ) -> None:
        self._provider        = provider
        self._mcp             = mcp_client
        self.max_tool_rounds  = max_tool_rounds
        self._system_prompt   = build_system_prompt()

        # Set by benchmark/run.py before each episode for richer prompts
        self.scenario_name: str = ""

        # Metrics accumulated over the benchmark run
        self.step_records:    list[dict] = []
        self.episode_rewards: list[float] = []

        # Compatibility shims expected by multi_step.py / train.py
        self.episode_reward_history: list[float] = []
        self.current_episode_reward: float = 0.0

    # -----------------------------------------------------------------------
    # Core interface
    # -----------------------------------------------------------------------

    def act(
        self,
        obs:           dict,
        namespace:     str  = "virtual-default",
        deploy:        str  = "web",
        step_idx:      int  = 0,
        max_steps:     int  = 10,
        scenario_name: str  = "",
        **_ignored: Any,   # absorbs unused kwargs from one_step.py
    ) -> int:
        """
        Choose an action by querying the LLM provider with MCP tools.

        Args:
            obs:           Raw observation {"ready": int, "pending": int, "total": int}
                           May also carry "target" injected by one_step.py.
            namespace:     Kubernetes namespace of the live simulation.
            deploy:        Deployment name to manage.
            step_idx:      Current step index within the episode (0-based).
            max_steps:     Max steps in the episode (shown in prompt).
            scenario_name: Human-readable scenario label (optional).

        Returns:
            Action index (int, 0-6) matching ACTION_SPACE in one_step.py.
        """
        _scenario = scenario_name or self.scenario_name

        user_message = build_user_message(
            obs           = obs,
            target        = obs.get("target", 0),
            namespace     = namespace,
            deploy        = deploy,
            step_idx      = step_idx,
            max_steps     = max_steps,
            scenario_name = _scenario,
        )

        t_start = time.time()

        result = self._provider.run_step(
            system_prompt   = self._system_prompt,
            user_message    = user_message,
            mcp_client      = self._mcp,
            anthropic_tools = self._mcp.anthropic_tools,
            max_tool_rounds = self.max_tool_rounds,
        )

        latency_s = time.time() - t_start

        logger.info(
            f"LLMAgent [{self._provider.model_name}]: "
            f"action={result.action_idx} "
            f"reasoning='{result.reasoning}' "
            f"tool_calls={result.tool_calls_made} "
            f"rounds={result.rounds} "
            f"latency={latency_s:.2f}s"
        )

        self._record_step(
            obs        = obs,
            action_idx = result.action_idx,
            reasoning  = result.reasoning,
            tool_calls = result.tool_calls_made,
            latency_s  = latency_s,
            rounds     = result.rounds,
        )

        return result.action_idx

    def update(self, *args: Any, **kwargs: Any) -> None:
        """No-op. LLMs do not update weights from experience."""
        pass

    # -----------------------------------------------------------------------
    # Persistence
    # -----------------------------------------------------------------------

    def save(self, path: str) -> None:
        """Save benchmark run metadata (not weights) to JSON."""
        data = {
            "provider":        self._provider.model_name,
            "max_tool_rounds": self.max_tool_rounds,
            "step_records":    self.step_records,
            "episode_rewards": self.episode_rewards,
        }
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
        logger.info(f"LLMAgent: saved metadata to {path}")

    def load(self, path: str) -> None:
        """Restore previously saved run metadata."""
        with open(path) as f:
            data = json.load(f)
        self.max_tool_rounds  = data.get("max_tool_rounds", self.max_tool_rounds)
        self.step_records     = data.get("step_records",    [])
        self.episode_rewards  = data.get("episode_rewards", [])
        logger.info(f"LLMAgent: loaded metadata from {path}")

    def reset(self) -> None:
        """Reset accumulated metrics (e.g. when reusing the agent across runs)."""
        self.step_records           = []
        self.episode_rewards        = []
        self.episode_reward_history = []
        self.current_episode_reward = 0.0

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    def _record_step(
        self,
        obs:        dict,
        action_idx: int,
        reasoning:  str,
        tool_calls: list[str],
        latency_s:  float,
        rounds:     int,
    ) -> None:
        self.step_records.append({
            "obs":        obs,
            "action_idx": action_idx,
            "reasoning":  reasoning,
            "tool_calls": tool_calls,
            "latency_s":  round(latency_s, 3),
            "rounds":     rounds,
        })
