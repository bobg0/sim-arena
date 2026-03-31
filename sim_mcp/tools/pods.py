"""sim_mcp/tools/pods.py"""
from ._k8s import get_core_v1


def get_pods(namespace: str) -> dict:
    """
    List all pods in a Kubernetes namespace with full status details.

    Returns pod phase (Running/Pending/Failed), container states
    (including waiting reason such as OOMKilled or CrashLoopBackOff),
    restart counts, and scheduling node.

    Args:
        namespace: Kubernetes namespace to query (e.g. "virtual-default")
    """
    v1 = get_core_v1()
    pod_list = v1.list_namespaced_pod(namespace=namespace)
    pods = []
    for pod in pod_list.items:
        conditions = []
        for c in pod.status.conditions or []:
            conditions.append({
                "type":    c.type,
                "status":  c.status,
                "reason":  c.reason or "",
                "message": c.message or "",
            })
        containers = []
        for cs in pod.status.container_statuses or []:
            state: dict = {}
            if cs.state.running:
                state["running"] = {"started_at": str(cs.state.running.started_at)}
            elif cs.state.waiting:
                state["waiting"] = {
                    "reason":  cs.state.waiting.reason or "",
                    "message": cs.state.waiting.message or "",
                }
            elif cs.state.terminated:
                state["terminated"] = {
                    "reason":    cs.state.terminated.reason or "",
                    "exit_code": cs.state.terminated.exit_code,
                }
            containers.append({
                "name":          cs.name,
                "ready":         cs.ready,
                "restart_count": cs.restart_count,
                "state":         state,
            })
        pods.append({
            "name":       pod.metadata.name,
            "phase":      pod.status.phase or "Unknown",
            "node_name":  pod.spec.node_name,
            "conditions": conditions,
            "containers": containers,
        })
    return {"namespace": namespace, "count": len(pods), "pods": pods}
