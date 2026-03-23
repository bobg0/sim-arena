"""
agent/providers/gemini_provider.py

Google Gemini provider for the Sim-Arena LLM agent.

Uses the current google-genai SDK (google.genai).
Reads GEMINI_API_KEY from the environment (loaded from .env).

Install:
    pip install google-genai

Supported models:
    gemini-2.0-flash          (fast, good for benchmarking — recommended)
    gemini-2.5-flash-preview  (stronger reasoning)
    gemini-2.5-pro-preview    (highest quality)
"""

from __future__ import annotations

import json
import logging
import os

from google import genai
from google.genai import types

from agent.providers.base import LLMProvider, StepResult
from agent import action_parser

logger = logging.getLogger("providers.gemini")

_DEFAULT_MODEL = "gemini-2.5-flash-lite"


class GeminiProvider(LLMProvider):
    """
    LLM provider backed by the Google Gemini API (google-genai SDK).

    Args:
        model: Gemini model string (default: "gemini-2.0-flash")
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
        """Run the Gemini function-calling loop for one agent step."""

        gemini_tools = _convert_tools(anthropic_tools)
        config = types.GenerateContentConfig(
            system_instruction = system_prompt,
            tools              = gemini_tools,
            temperature        = 0.0,
            max_output_tokens  = 1024,
        )

        # Conversation history — list of types.Content
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

            # ---- tool call round cap -------------------------------------
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
                            "your JSON action object and nothing else."
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

            # ---- execute tool calls and add results to history -----------
            # Append the model's response (with function calls) to history
            contents.append(response.candidates[0].content)

            fn_response_parts: list[types.Part] = []
            for fn_call in fn_calls:
                tool_name = fn_call.name
                tool_args = dict(fn_call.args)
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
# Tool schema conversion: Anthropic JSON Schema → Gemini types.Tool
# ---------------------------------------------------------------------------

def _convert_tools(anthropic_tools: list[dict]) -> list[types.Tool]:
    """
    Convert Anthropic-format tool definitions to a Gemini types.Tool object.

    Anthropic format:
        {"name": str, "description": str, "input_schema": {JSON Schema}}

    Gemini format:
        types.Tool(function_declarations=[types.FunctionDeclaration(...)])
    """
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
    """
    Recursively convert a JSON Schema dict to a types.Schema object.
    Handles object, array, and scalar types.
    """
    schema_type = schema.get("type", "object").upper()

    kwargs: dict = {
        "type":        schema_type,
        "description": schema.get("description", ""),
    }

    if schema_type == "OBJECT":
        raw_props = schema.get("properties", {})
        if raw_props:
            kwargs["properties"] = {
                k: _json_schema_to_gemini(v)
                for k, v in raw_props.items()
            }
        if "required" in schema:
            kwargs["required"] = schema["required"]

    elif schema_type == "ARRAY":
        items = schema.get("items", {})
        kwargs["items"] = _json_schema_to_gemini(items)

    elif schema_type == "STRING" and "enum" in schema:
        kwargs["enum"] = schema["enum"]

    return types.Schema(**kwargs)


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------

def _extract_function_calls(response) -> list:
    """Return all function_call parts from a Gemini response."""
    calls = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.function_call:
                calls.append(part.function_call)
    return calls


def _extract_text(response) -> str:
    """Extract concatenated text from a Gemini response."""
    parts = []
    for candidate in response.candidates:
        for part in candidate.content.parts:
            if part.text:
                parts.append(part.text)
    return "\n".join(parts).strip()
