"""
agent/providers/anthropic_provider.py

Anthropic Claude provider for the Sim-Arena LLM agent.

Reads ANTHROPIC_API_KEY from the environment (loaded from .env by
agent/llm_agent.py at import time via python-dotenv).
"""

from __future__ import annotations

import logging

import anthropic

from agent.providers.base import LLMProvider, StepResult
from agent import action_parser

logger = logging.getLogger("providers.anthropic")

_MAX_TOKENS = 1024


class AnthropicProvider(LLMProvider):
    """
    LLM provider backed by the Anthropic Messages API.

    Args:
        model: Anthropic model string, e.g. "claude-sonnet-4-20250514"
    """

    def __init__(self, model: str = "claude-sonnet-4-20250514") -> None:
        self._model  = model
        self._client = anthropic.Anthropic()   # reads ANTHROPIC_API_KEY from env

    @property
    def model_name(self) -> str:
        return self._model

    def run_step(
        self,
        system_prompt:   str,
        user_message:    str,
        mcp_client,
        anthropic_tools: list[dict],
        max_tool_rounds: int,
    ) -> StepResult:
        """Run the Anthropic tool-use loop for one agent step."""

        messages: list[dict]   = [{"role": "user", "content": user_message}]
        tool_calls_made: list[str] = []

        for round_idx in range(max_tool_rounds + 1):
            response = self._client.messages.create(
                model      = self._model,
                max_tokens = _MAX_TOKENS,
                system     = system_prompt,
                tools      = anthropic_tools,
                messages   = messages,
            )

            # ---- final text response -------------------------------------
            if response.stop_reason == "end_turn":
                text = _extract_text(response)
                action_idx, reasoning = action_parser.parse(text)
                return StepResult(
                    action_idx      = action_idx,
                    reasoning       = reasoning,
                    tool_calls_made = tool_calls_made,
                    rounds          = round_idx,
                )

            # ---- tool use ------------------------------------------------
            if response.stop_reason == "tool_use":
                tool_blocks = [b for b in response.content if b.type == "tool_use"]

                if not tool_blocks:
                    break

                if round_idx >= max_tool_rounds:
                    # Force a final answer without more tool calls
                    messages.append({"role": "assistant", "content": response.content})
                    messages.append({
                        "role": "user",
                        "content": (
                            "You have reached the maximum number of tool calls. "
                            "Based on what you have seen so far, respond NOW with "
                            "your JSON action object and nothing else."
                        ),
                    })
                    final = self._client.messages.create(
                        model      = self._model,
                        max_tokens = _MAX_TOKENS,
                        system     = system_prompt,
                        messages   = messages,
                    )
                    text = _extract_text(final)
                    action_idx, reasoning = action_parser.parse(text)
                    return StepResult(
                        action_idx      = action_idx,
                        reasoning       = reasoning,
                        tool_calls_made = tool_calls_made,
                        rounds          = round_idx + 1,
                    )

                # Execute tool calls and collect results
                messages.append({"role": "assistant", "content": response.content})
                tool_results = []
                for block in tool_blocks:
                    tool_calls_made.append(block.name)
                    logger.debug(f"Tool call: {block.name}({block.input})")
                    result_str = mcp_client.call_tool(block.name, block.input)
                    tool_results.append({
                        "type":        "tool_result",
                        "tool_use_id": block.id,
                        "content":     result_str,
                    })
                messages.append({"role": "user", "content": tool_results})
                continue

            break  # unexpected stop_reason

        logger.error("Anthropic provider: loop ended without final action. Defaulting to noop.")
        return StepResult(action_idx=0, reasoning="fallback noop", tool_calls_made=tool_calls_made)


def _extract_text(response) -> str:
    return "\n".join(
        b.text for b in response.content if hasattr(b, "text")
    ).strip()
