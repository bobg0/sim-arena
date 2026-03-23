"""sim_mcp/tools/events.py"""
from __future__ import annotations
from ._k8s import get_core_v1


def get_events(namespace: str, deploy: str | None = None, last_n: int = 20) -> dict:
    """
    Fetch recent Kubernetes events, optionally filtered to a deployment.

    Warning events are sorted first. Use this to diagnose why pods are
    failing (OOMKilled, Insufficient CPU, FailedScheduling, etc.).

    Args:
        namespace: Kubernetes namespace          (e.g. "virtual-default")
        deploy:    Deployment name filter        (e.g. "web"; optional)
        last_n:    Max events to return          (default 20)
    """
    v1 = get_core_v1()
    event_list = v1.list_namespaced_event(namespace=namespace)
    events = []
    for ev in event_list.items:
        obj_name = ev.involved_object.name or ""
        if deploy is not None:
            if not (obj_name == deploy or obj_name.startswith(f"{deploy}-")):
                continue
        last_ts = str(ev.last_timestamp or ev.event_time or "")
        events.append({
            "type":           ev.type or "Normal",
            "reason":         ev.reason or "",
            "message":        ev.message or "",
            "object_kind":    ev.involved_object.kind or "",
            "object_name":    obj_name,
            "count":          ev.count or 1,
            "last_timestamp": last_ts,
            "_is_warning":    (ev.type or "") == "Warning",
        })
    events.sort(key=lambda e: (not e.pop("_is_warning"), e["last_timestamp"]))
    return {
        "namespace":      namespace,
        "deploy_filter":  deploy,
        "total_returned": len(events[:last_n]),
        "events":         events[:last_n],
    }
