"""Actions package for manipulating SimArena traces."""

from .trace_io import load_trace, save_trace  # noqa: F401
from .ops import (  # noqa: F401
    bump_cpu_small,
    bump_mem_small,
    scale_up_replicas,
)

__all__ = [
    "load_trace",
    "save_trace",
    "bump_cpu_small",
    "bump_mem_small",
    "scale_up_replicas",
]

