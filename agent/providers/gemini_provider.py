"""
agent/providers/gemini_provider.py

Google Gemini provider for the Sim-Arena LLM agent.
Uses the current google-genai SDK (google.genai).
Reads GEMINI_API_KEY from the environment (loaded from .env).

Install:
    pip install google-genai
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

from google import genai
from google.genai import types

from agent.providers.base import LLMProvider, StepResult
from agent import action_parser

logger = logging.getLogger("providers.gemini")

_DEFAULT_MODEL   = "gemini-2.5-flash-lite"
_MAX_RETRIES     = 3
_RETRY_DELAY_S   = 30   # seconds to wait after a 503


class GeminiProvider(LLMProvider):
    """
    LLM provider backed by the Google Gemini API (google-genai SDK).

    Args:
        model: Gemini model string (default: "gemini-2.5-flash-lite")
    """

    def __init__(self, model: str = _DEFAULT_MODEL) -> None:
        self._model_name = model
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            raise EnvironmentError(
                "GEMINI_API_KEY is not set. "
                "Add it to your .env file (see .env.example)."
            )
        self._client = genai.Client(api_key=api_key)

    @property
    def model_name(self) -> str:
        return self._model_name

    def run_step(
        self,
        system_prompt:   str,
        user_message:    str,
        mcp_client,
        anthropic_tools: list[dict],
        max_tool_rounds: int,
    ) -> StepResult:
        """Run the Gemini function-calling loop with retry on 503."""
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                return self._run_step_once(
                    system_prompt, user_message, mcp_client,
                    anthropic_tools, max_tool_rounds,
                )
            except Exception as exc:
                err_str = str(exc)
                is_503  = "503" in err_str or "UNAVAILABLE" in err_str
                is_429  = "429" in err_str or "RESOURCE_EXHAUSTED" in err_str

                if (is_503 or is_429) and attempt < _MAX_RETRIES:
                    wait = _RETRY_DELAY_S * attempt
                    logger.warning(
                        f"Gemini API transient error (attempt {attempt}/{_MAX_RETRIES}): "
                        f"{err_str[:120]}. Retrying in {wait}s..."
                    )
                    time.sleep(wait)
                    continue

                # Non-retryable or exhausted retries — re-raise so benchmark
                # can record the failure and move on to the next scenario.
                raise

        # Should never reach here
        raise RuntimeError("Gemini provider: retry loop exited without result")

    def _run_step_once(
        self,
        system_prompt:   str,
        user_message:    str,
        mcp_client,
        anthropic_tools: list[dict],
        max_tool_rounds: int,
    ) -> StepResult:
        """Single attempt at the Gemini function-calling loop."""
        gemini_tools = _convert_tools(anthropic_tools)
        config = types.GenerateContentConfig(
            system_instruction = system_prompt,
            tools              = gemini_tools,
            temperature        = 0.0,
            max_output_tokens  = 1024,
        )

        contents: list[types.Content] = [
            types.Content(
                role  = "user",
                parts = [types.Part(text=user_message)],
            )
        ]

        tool_calls_made: list[str] = []

        for round_idx in range(max_tool_rounds + 1):
            response = self._client.models.generate_content(
                model    = self._model_name,
                contents = contents,
                config   = config,
            )

            fn_calls = _extract_function_calls(response)

            # ---- no tool calls → parse action from text ------------------
            if not fn_calls:
                text = _extract_text(response)
                action_idx, reasoning = action_parser.parse(text)
                return StepResult(
                    action_idx      = action_idx,
                    reasoning       = reasoning,
                    tool_calls_made = tool_calls_made,
                    rounds          = round_idx,
                )

            # ---- tool call round cap ------------------------------------
            if round_idx >= max_tool_rounds:
                logger.warning(
                    f"Gemini provider: hit max_tool_rounds ({max_tool_rounds}). "
                    "Asking for final answer."
                )
                contents.append(
                    types.Content(
                        role  = "user",
                        parts = [types.Part(text=(
                            "You have reached the maximum number of tool calls. "
                            "Based on what you have seen so far, respond NOW with "
                            "your JSON action object and nothing else.\n"
                            '{"action_index": <0-6>, "reasoning": "<one sentence>"}'
                        ))],
                    )
                )
                final = self._client.models.generate_content(
                    model    = self._model_name,
                    contents = contents,
                    config   = config,
                )
                text = _extract_text(final)
                action_idx, reasoning = action_parser.parse(text)
                return StepResult(
                    action_idx      = action_idx,
                    reasoning       = reasoning,
                    tool_calls_made = tool_calls_made,
                    rounds          = round_idx + 1,
                )

            # ---- execute tool calls — only accept the 4 MCP tools -------
            contents.append(response.candidates[0].content)
            fn_response_parts: list[types.Part] = []

            valid_tool_names = {t["name"] for t in anthropic_tools}

            for fn_call in fn_calls:
                tool_name = fn_call.name
                tool_args = dict(fn_call.args)

                if tool_name not in valid_tool_names:
                    # LLM called an action name as a tool — reject it and
                    # explain what happened so it corrects itself.
                    logger.debug(
                        f"Gemini tried to call non-tool '{tool_name}' — rejecting."
                    )
                    fn_response_parts.append(
                        types.Part.from_function_response(
                            name     = tool_name,
                            response = {
                                "error": (
                                    f"'{tool_name}' is not a callable tool. "
                                    "The only callable tools are: "
                                    + ", ".join(sorted(valid_tool_names))
                                    + ". To act, return JSON: "
                                    '{"action_index": <0-6>, "reasoning": "..."}.'
                                )
                            },
                        )
                    )
                    tool_calls_made.append(f"INVALID:{tool_name}")
                    continue

                tool_calls_made.append(tool_name)
                logger.debug(f"Tool call: {tool_name}({tool_args})")
                result_str = mcp_client.call_tool(tool_name, tool_args)

                try:
                    result_dict = json.loads(result_str)
                except (json.JSONDecodeError, ValueError):
                    result_dict = {"result": result_str}

                fn_response_parts.append(
                    types.Part.from_function_response(
                        name     = tool_name,
                        response = result_dict,
                    )
                )

            contents.append(
                types.Content(role="user", parts=fn_response_parts)
            )

        logger.error("Gemini provider: loop ended without final action. Defaulting to noop.")
        return StepResult(action_idx=0, reasoning="fallback noop", tool_calls_made=tool_calls_made)


# ---------------------------------------------------------------------------
# Tool schema conversion
# ---------------------------------------------------------------------------

def _convert_tools(anthropic_tools: list[dict]) -> list[types.Tool]:
    fn_declarations = []
    for tool in anthropic_tools:
        fn_declarations.append(
            types.FunctionDeclaration(
                name        = tool["name"],
                description = tool.get("description", ""),
                parameters  = _json_schema_to_gemini(tool.get("input_schema", {})),
            )
        )
    return [types.Tool(function_declarations=fn_declarations)]


def _json_schema_to_gemini(schema: dict) -> types.Schema:
    schema_type = schema.get("type", "object").upper()
    kwargs: dict[str, Any] = {
        "type":        schema_type,
        "description": schema.get("description", ""),
    }
    if schema_type == "OBJECT":
        raw_props = schema.get("properties", {})
        if raw_props:
            kwargs["properties"] = {
                k: _json_schema_to_gemini(v) for k, v in raw_props.items()
            }
        if "required" in schema:
            kwargs["required"] = schema["required"]
    elif schema_type == "ARRAY":
        kwargs["items"] = _json_schema_to_gemini(schema.get("items", {}))
    elif schema_type == "STRING" and "enum" in schema:
        kwargs["enum"] = schema["enum"]
    return types.Schema(**kwargs)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _extract_function_calls(response) -> list:
    calls = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call and part.function_call.name:
                calls.append(part.function_call)
    return calls


def _extract_text(response) -> str:
    parts = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.text:
                parts.append(part.text)
    return "\n".join(parts).strip()