"""
agent/providers/base.py

Abstract base class for LLM providers.

Each provider owns the full tool-use loop for a single agent step:
  system prompt + user message → [tool calls] → action index + metadata

This keeps all provider-specific API logic (message format, tool schema
format, stop-reason handling) inside the provider, while LLMAgent and
the benchmark runner remain provider-agnostic.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class StepResult:
    """Structured result from one agent step (one run_step() call)."""
    action_idx:      int
    reasoning:       str
    tool_calls_made: list[str] = field(default_factory=list)
    rounds:          int = 0


class LLMProvider(ABC):
    """
    Abstract LLM provider.

    Subclasses implement run_step(), which runs the full tool-use
    conversation loop for a single Sim-Arena agent step and returns
    a StepResult with the chosen action index.
    """

    @abstractmethod
    def run_step(
        self,
        system_prompt:   str,
        user_message:    str,
        mcp_client,                  # MCPClientSync
        anthropic_tools: list[dict], # Anthropic-format tool defs from MCP
        max_tool_rounds: int,
    ) -> StepResult:
        """
        Run the tool-use loop for one agent step.

        Args:
            system_prompt:   The static system prompt from prompt_builder.
            user_message:    The per-step user message from prompt_builder.
            mcp_client:      MCPClientSync instance for executing tool calls.
            anthropic_tools: Tool definitions in Anthropic schema format
                             (as returned by MCPClientSync.anthropic_tools).
                             Providers must convert these to their own format.
            max_tool_rounds: Hard cap on tool-call rounds.

        Returns:
            StepResult with action_idx (0-6), reasoning, tool_calls_made, rounds.
        """
        ...

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Human-readable model identifier for logging and reports."""
        ...
