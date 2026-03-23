"""sim_mcp/tools/_k8s.py — shared Kubernetes client loader."""
from kubernetes import client, config


def get_core_v1() -> client.CoreV1Api:
    _load_config()
    return client.CoreV1Api()


def get_apps_v1() -> client.AppsV1Api:
    _load_config()
    return client.AppsV1Api()


def _load_config() -> None:
    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
