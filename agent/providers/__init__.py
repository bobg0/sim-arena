"""
agent/providers/__init__.py

Factory for creating LLM providers by name.
"""

from __future__ import annotations

from agent.providers.base import LLMProvider, StepResult
from agent.providers.anthropic_provider import AnthropicProvider
from agent.providers.gemini_provider import GeminiProvider

__all__ = [
    "LLMProvider",
    "StepResult",
    "AnthropicProvider",
    "GeminiProvider",
    "make_provider",
]

# Maps --provider CLI flag values to provider classes and default models
_PROVIDER_DEFAULTS = {
    "anthropic": ("claude-sonnet-4-20250514", AnthropicProvider),
    "gemini":    ("gemini-2.5-flash-lite",         GeminiProvider),
}


def make_provider(provider: str, model: str | None = None) -> LLMProvider:
    """
    Create an LLMProvider by provider name.

    Args:
        provider: "anthropic" or "gemini"
        model:    Optional model override. If None, uses the provider default.

    Returns:
        Configured LLMProvider instance.

    Raises:
        ValueError: if provider name is not recognised.
    """
    if provider not in _PROVIDER_DEFAULTS:
        raise ValueError(
            f"Unknown provider '{provider}'. "
            f"Choose from: {list(_PROVIDER_DEFAULTS.keys())}"
        )
    default_model, cls = _PROVIDER_DEFAULTS[provider]
    return cls(model=model or default_model)
