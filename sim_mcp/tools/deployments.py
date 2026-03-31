"""sim_mcp/tools/deployments.py"""
from ._k8s import get_apps_v1


def describe_deployment(namespace: str, deploy: str) -> dict:
    """
    Describe a Deployment's current resource configuration and rollout status.

    Returns CPU/memory requests, desired vs ready replica counts, and conditions.

    Args:
        namespace: Kubernetes namespace  (e.g. "virtual-default")
        deploy:    Deployment name       (e.g. "web")
    """
    apps_v1 = get_apps_v1()
    d = apps_v1.read_namespaced_deployment(name=deploy, namespace=namespace)
    s = d.status
    replicas = {
        "desired":     d.spec.replicas or 0,
        "ready":       s.ready_replicas or 0,
        "available":   s.available_replicas or 0,
        "unavailable": s.unavailable_replicas or 0,
    }
    containers = []
    for c in d.spec.template.spec.containers:
        res = c.resources or {}
        requests = {k: str(v) for k, v in res.requests.items()} if res.requests else {}
        limits   = {k: str(v) for k, v in res.limits.items()}   if res.limits   else {}
        containers.append({
            "name":  c.name,
            "image": c.image or "",
            "resources": {"requests": requests, "limits": limits},
        })
    conditions = []
    for cond in d.status.conditions or []:
        conditions.append({
            "type":    cond.type,
            "status":  cond.status,
            "reason":  cond.reason or "",
            "message": cond.message or "",
        })
    return {
        "name":       deploy,
        "namespace":  namespace,
        "replicas":   replicas,
        "containers": containers,
        "conditions": conditions,
    }
