"""benchmark/scenarios/__init__.py"""

from __future__ import annotations

import json
from pathlib import Path

_INDEX = Path(__file__).parent / "index.json"


def load_scenarios(filter_type: str | None = None) -> list[dict]:
    """
    Load benchmark scenarios from index.json.

    Args:
        filter_type: Optional problem_type to filter by
                     (e.g. "cpu_insufficient", "mem_insufficient",
                      "replica_deficit", "combined", "over_allocation")

    Returns:
        List of scenario dicts, each with keys:
            name, trace, target, problem_type, description
    """
    with open(_INDEX) as f:
        data = json.load(f)

    scenarios = data["scenarios"]

    if filter_type is not None:
        scenarios = [s for s in scenarios if s["problem_type"] == filter_type]

    return scenarios
