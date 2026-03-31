"""
sim_mcp/server.py

FastMCP server exposing four Kubernetes observability tools.
Runs as a stdio subprocess started by sim_mcp/client.py.

Usage (standalone test):
    python sim_mcp/server.py
"""

import sys
from pathlib import Path

_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from mcp.server.fastmcp import FastMCP

from sim_mcp.tools.pods import get_pods as _get_pods
from sim_mcp.tools.deployments import describe_deployment as _describe_deployment
from sim_mcp.tools.events import get_events as _get_events
from sim_mcp.tools.logs import get_pod_logs as _get_pod_logs

mcp = FastMCP(
    name="sim-arena-k8s"
)


@mcp.tool()
def get_pods(namespace: str) -> dict:
    """
    List all pods in a Kubernetes namespace with full status details.

    Returns pod phase (Running/Pending/Failed), container states
    (including waiting reason such as OOMKilled or CrashLoopBackOff),
    restart counts, and scheduling node.

    Use this as your first call to understand how many pods are healthy
    vs. stuck, and why they are stuck.

    Args:
        namespace: Kubernetes namespace to query (e.g. "virtual-default")
    """
    return _get_pods(namespace=namespace)


@mcp.tool()
def describe_deployment(namespace: str, deploy: str) -> dict:
    """
    Describe a Deployment's current resource configuration and rollout status.

    Returns the current CPU and memory requests/limits for every container,
    desired vs. ready vs. unavailable replica counts, and deployment conditions.

    Use this to understand exactly what resources the pods are currently
    requesting before deciding whether to bump, reduce, or scale.

    Args:
        namespace: Kubernetes namespace  (e.g. "virtual-default")
        deploy:    Deployment name       (e.g. "web")
    """
    return _describe_deployment(namespace=namespace, deploy=deploy)


@mcp.tool()
def get_events(
    namespace: str,
    deploy: str | None = None,
    last_n: int = 20,
) -> dict:
    """
    Fetch recent Kubernetes events for a namespace, filtered to a deployment.

    Warning events (OOMKilling, FailedScheduling, Insufficient CPU/memory,
    BackOff) are returned first so the most actionable signals are visible
    immediately.

    Args:
        namespace: Kubernetes namespace          (e.g. "virtual-default")
        deploy:    Deployment name filter        (e.g. "web"; optional)
        last_n:    Max events to return          (default 20)
    """
    return _get_events(namespace=namespace, deploy=deploy, last_n=last_n)


@mcp.tool()
def get_pod_logs(
    namespace:  str,
    pod_name:   str,
    tail_lines: int = 50,
    container:  str | None = None,
) -> dict:
    """
    Fetch the last N log lines from a specific pod's container.

    Use this when events alone don't explain a failure.
    You can get pod names from get_pods().

    Args:
        namespace:  Kubernetes namespace        (e.g. "virtual-default")
        pod_name:   Full pod name               (e.g. "web-6d4f9b-xz7kp")
        tail_lines: Lines to fetch from the end (default 50)
        container:  Container name (optional; defaults to first container)
    """
    return _get_pod_logs(
        namespace=namespace,
        pod_name=pod_name,
        tail_lines=tail_lines,
        container=container,
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
