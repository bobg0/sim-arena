"""sim_mcp/tools/logs.py"""
from __future__ import annotations
from ._k8s import get_core_v1


def get_pod_logs(
    namespace:  str,
    pod_name:   str,
    tail_lines: int = 50,
    container:  str | None = None,
) -> dict:
    """
    Fetch the last N log lines from a pod container.

    Use this when events alone don't explain a failure.
    Get pod names from get_pods().

    Args:
        namespace:  Kubernetes namespace        (e.g. "virtual-default")
        pod_name:   Full pod name               (e.g. "web-6d4f9b-xz7kp")
        tail_lines: Lines to fetch from the end (default 50)
        container:  Container name (optional; defaults to first container)
    """
    v1 = get_core_v1()
    resolved = container
    if resolved is None:
        try:
            pod = v1.read_namespaced_pod(name=pod_name, namespace=namespace)
            resolved = pod.spec.containers[0].name
        except Exception as exc:
            return {
                "namespace": namespace, "pod_name": pod_name,
                "container": "", "tail_lines": tail_lines,
                "logs": "", "error": f"Could not resolve container: {exc}",
            }
    try:
        logs = v1.read_namespaced_pod_log(
            name=pod_name, namespace=namespace,
            container=resolved, tail_lines=tail_lines, timestamps=True,
        )
        error = ""
    except Exception as exc:
        logs  = ""
        error = str(exc)
    return {
        "namespace": namespace, "pod_name": pod_name,
        "container": resolved,  "tail_lines": tail_lines,
        "logs": logs,           "error": error,
    }
