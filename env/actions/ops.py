"""Operations for mutating trace objects in a controlled way."""

from __future__ import annotations

import re
from typing import Any, Iterator, Mapping, MutableMapping


_CPU_RE = re.compile(r"^([0-9]*\.?[0-9]+)(m?)$")
_MEM_RE = re.compile(r"^([0-9]*\.?[0-9]+)([a-zA-Z]*)$")

_MEM_FACTORS = {
    "": 1,
    "B": 1,
    "Ki": 1024,
    "Mi": 1024**2,
    "Gi": 1024**3,
    "Ti": 1024**4,
}


def _iter_deployments(obj: Mapping[str, Any], deploy: str) -> Iterator[MutableMapping[str, Any]]:
    for event in obj.get("events", []):
        for applied in event.get("applied_objs", []):
            if not isinstance(applied, MutableMapping):
                continue
            if applied.get("kind") != "Deployment":
                continue
            meta = applied.get("metadata") or {}
            if meta.get("name") == deploy:
                yield applied


def _first_container(deployment: MutableMapping[str, Any]) -> MutableMapping[str, Any] | None:
    spec = deployment.get("spec") or {}
    template = spec.get("template") or {}
    pod_spec = template.get("spec") or {}
    containers = pod_spec.get("containers") or []
    if not containers:
        return None
    container = containers[0]
    if isinstance(container, MutableMapping):
        return container
    return None


def _ensure_requests(container: MutableMapping[str, Any]) -> MutableMapping[str, Any]:
    resources = container.get("resources")
    if not isinstance(resources, MutableMapping):
        resources = {}
        container["resources"] = resources

    requests = resources.get("requests")
    if not isinstance(requests, MutableMapping):
        requests = {}
        resources["requests"] = requests

    return requests


def _parse_cpu(quantity: Any) -> tuple[int, str]:
    if quantity in (None, ""):
        return 0, "m"
    text = str(quantity).strip()
    match = _CPU_RE.match(text)
    if not match:
        raise ValueError(f"Unsupported CPU quantity: {quantity}")
    number, unit = match.groups()
    value = float(number)
    if unit == "m":
        millicores = int(round(value))
        return millicores, "m"

    unit = unit or ""
    millicores = int(round(value * 1000))
    return millicores, unit


def _format_cpu(millicores: int, preferred_unit: str) -> str:
    if preferred_unit == "":
        cores = millicores / 1000
        if cores.is_integer():
            return str(int(cores))
        return f"{cores:.3f}".rstrip("0").rstrip(".")
    preferred = preferred_unit or "m"
    if preferred == "m":
        return f"{millicores}m"
    cores = millicores / 1000
    if cores.is_integer():
        return str(int(cores))
    return f"{cores:.3f}".rstrip("0").rstrip(".")


def _parse_mem(quantity: Any) -> tuple[int, str]:
    if quantity in (None, ""):
        return 0, "Mi"
    text = str(quantity).strip()
    match = _MEM_RE.match(text)
    if not match:
        raise ValueError(f"Unsupported memory quantity: {quantity}")
    number, unit = match.groups()
    unit = unit or "B"
    factor = _MEM_FACTORS.get(unit)
    if factor is None:
        raise ValueError(f"Unsupported memory unit: {unit}")
    bytes_val = int(round(float(number) * factor))
    return bytes_val, unit


def _format_mem(bytes_val: int, preferred_unit: str) -> str:
    unit = preferred_unit if preferred_unit in _MEM_FACTORS else "Mi"
    factor = _MEM_FACTORS[unit]
    if factor and bytes_val % factor == 0:
        value = bytes_val // factor
        return f"{value}{unit}" if unit else str(value)
    if unit != "Mi":
        return _format_mem(bytes_val, "Mi")
    value = bytes_val / factor
    return f"{value:.2f}Mi"


def bump_cpu_small(obj: MutableMapping[str, Any], deploy: str, step: str = "500m") -> bool:
    """Increase CPU requests for the first container by *step*.

    Returns True when at least one Deployment is updated.
    """

    try:
        step_value, step_unit = _parse_cpu(step)
    except ValueError as exc:
        raise ValueError(f"Invalid CPU step '{step}': {exc}") from exc

    changed = False
    for deployment in _iter_deployments(obj, deploy):
        container = _first_container(deployment)
        if container is None:
            continue

        requests = _ensure_requests(container)
        current_raw = requests.get("cpu")
        current_value, current_unit = _parse_cpu(current_raw)
        new_value = current_value + step_value
        preferred_unit = current_unit if current_raw not in (None, "") else step_unit
        requests["cpu"] = _format_cpu(new_value, preferred_unit)
        changed = True

    return changed


def bump_mem_small(obj: MutableMapping[str, Any], deploy: str, step: str = "256Mi") -> bool:
    """Increase memory requests for the first container by *step*."""

    try:
        step_value, step_unit = _parse_mem(step)
    except ValueError as exc:
        raise ValueError(f"Invalid memory step '{step}': {exc}") from exc

    changed = False
    for deployment in _iter_deployments(obj, deploy):
        container = _first_container(deployment)
        if container is None:
            continue

        requests = _ensure_requests(container)
        current_raw = requests.get("memory")
        current_value, current_unit = _parse_mem(current_raw)
        new_value = current_value + step_value
        preferred_unit = current_unit if current_raw not in (None, "") else step_unit
        requests["memory"] = _format_mem(new_value, preferred_unit)
        changed = True

    return changed


def scale_up_replicas(obj: MutableMapping[str, Any], deploy: str, delta: int = 1) -> bool:
    """Increase the replica count for *deploy* by *delta*."""

    if delta <= 0:
        raise ValueError("delta must be positive")

    changed = False
    for deployment in _iter_deployments(obj, deploy):
        spec = deployment.get("spec")
        if not isinstance(spec, MutableMapping):
            continue
        replicas = spec.get("replicas", 0)
        try:
            replicas_int = int(replicas)
        except (TypeError, ValueError):
            replicas_int = 0
        spec["replicas"] = replicas_int + delta
        changed = True

    return changed

