"""
agent/action_parser.py

Parses the LLM's final text response into an action index (0-6) that
maps directly to ACTION_SPACE in runner/one_step.py.

The LLM is instructed to return JSON with an "action_index" field.
This module handles malformed responses gracefully so a bad LLM output
never crashes the training loop — it falls back to action 0 (noop)
and logs the failure for later inspection.
"""

from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger("action_parser")

# Must match ACTION_SPACE in runner/one_step.py
VALID_ACTION_INDICES = frozenset(range(7))   # 0-6
FALLBACK_ACTION     = 0                       # noop


def parse(response_text: str) -> tuple[int, str]:
    """
    Parse the LLM's response text into an action index.

    Tries three strategies in order:
      1. Direct JSON parse of the full response.
      2. Extract the first {...} JSON object found via regex (handles prose + JSON).
      3. Scan for a bare integer in the text as a last resort.

    Args:
        response_text: The raw text content from the Anthropic API response.

    Returns:
        (action_index, reasoning) where:
          - action_index is an integer in 0-6
          - reasoning is the LLM's one-line explanation (or empty string)
    """
    text = (response_text or "").strip()

    # Strategy 1: full JSON parse
    action_idx, reasoning = _try_full_json(text)
    if action_idx is not None:
        return _clamp(action_idx), reasoning

    # Strategy 2: extract first {...} block
    action_idx, reasoning = _try_extract_json_block(text)
    if action_idx is not None:
        return _clamp(action_idx), reasoning

    # Strategy 3: bare integer anywhere in the text
    action_idx = _try_bare_integer(text)
    if action_idx is not None:
        logger.warning(
            "action_parser: fell back to bare integer extraction "
            f"(response was not valid JSON). action_index={action_idx}. "
            f"Raw response: {text[:200]}"
        )
        return _clamp(action_idx), ""

    # Total failure — use noop
    logger.error(
        "action_parser: could not extract action from LLM response. "
        f"Defaulting to noop (0). Raw response: {text[:200]}"
    )
    return FALLBACK_ACTION, ""


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _try_full_json(text: str) -> tuple[int | None, str]:
    """Attempt to parse the entire text as a JSON object."""
    try:
        data = json.loads(text)
        return _extract_from_dict(data)
    except (json.JSONDecodeError, ValueError):
        return None, ""


def _try_extract_json_block(text: str) -> tuple[int | None, str]:
    """Find the first {...} substring and try parsing it as JSON."""
    match = re.search(r"\{[^{}]*\}", text, re.DOTALL)
    if not match:
        return None, ""
    try:
        data = json.loads(match.group())
        return _extract_from_dict(data)
    except (json.JSONDecodeError, ValueError):
        return None, ""


def _try_bare_integer(text: str) -> int | None:
    """Scan for the first standalone integer in [0, 6]."""
    for token in re.split(r"\s+|,|;|\n", text):
        token = token.strip().strip('"').strip("'")
        try:
            val = int(token)
            if val in VALID_ACTION_INDICES:
                return val
        except ValueError:
            continue
    return None


def _extract_from_dict(data: dict) -> tuple[int | None, str]:
    """Pull action_index and reasoning out of a parsed JSON dict."""
    # Accept "action_index" or "action" as key names
    raw = data.get("action_index", data.get("action"))
    if raw is None:
        return None, ""
    try:
        idx = int(raw)
    except (ValueError, TypeError):
        return None, ""
    reasoning = str(data.get("reasoning", ""))
    return idx, reasoning


def _clamp(action_idx: int) -> int:
    """Ensure the action index is within the valid range."""
    if action_idx not in VALID_ACTION_INDICES:
        logger.warning(
            f"action_parser: action_index {action_idx} out of range [0-6]. "
            "Clamping to noop (0)."
        )
        return FALLBACK_ACTION
    return action_idx
