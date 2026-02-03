# observe/reader.py
# NOTE: Avoid failing at import time if kubernetes or kubeconfig is unavailable.
try:
    from kubernetes import client, config  # type: ignore
except Exception:  # pragma: no cover - environment-specific
    client = None  # type: ignore
    config = None  # type: ignore

# Lazily initialize API clients; keep module attributes for easy patching in tests.
v1 = None
apps_v1 = None

def _ensure_clients():
    global v1, apps_v1
    if v1 is not None and apps_v1 is not None:
        return
    if client is None or config is None:
        # Leave as None; tests can patch v1/apps_v1.
        return
    # Load kubeconfig from ~/.kube/config and create clients
    try:  # pragma: no cover - depends on environment
        config.load_kube_config()
        v1 = client.CoreV1Api()
        apps_v1 = client.AppsV1Api()
    except Exception:
        # Leave as None if we cannot initialize; functions handle None gracefully.
        v1 = None
        apps_v1 = None

def observe(namespace: str, deployment_name: str) -> dict:
    """
    Observes a specific deployment in a namespace and returns pod counts.
    
    NOTE: This assumes the deployment's pods are findable using a 
    label selector 'app: <deployment_name>'
    """
    
    # This label selector is an assumption, but a very common one.
    # It's the key to linking pods to the 'web' deployment.
    label_selector = f"app={deployment_name}"
    
    # Ensure clients exist (no-op in tests where v1 is patched)
    _ensure_clients()

    try:
        # List all pods in the namespace that match the label
        if v1 is None:
            raise RuntimeError("Kubernetes client not initialized")
        pod_list = v1.list_namespaced_pod(namespace=namespace, label_selector=label_selector)
        
        ready = 0
        pending = 0
        total = len(pod_list.items)
        
        for pod in pod_list.items:
            # Check if pod is Pending
            if pod.status.phase == "Pending":
                pending += 1
                continue # A pending pod can't be ready
            
            # Check if pod is Ready
            # A pod is "Ready" if its 'Ready' condition is 'True'
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == "Ready" and condition.status == "True":
                        ready += 1
                        break
                        
        return {"ready": ready, "pending": pending, "total": total}

    except Exception as e:
        print(f"Error observing pods: {e}")
        # On error, return a "safe" empty/zero state
        return {"ready": 0, "pending": 0, "total": 0}

def current_requests(namespace: str, deploy: str) -> dict:
    """
    Gets the *current* CPU/Memory requests for a deployment's first container.
    """
    # Ensure clients exist
    _ensure_clients()

    try:
        if apps_v1 is None:
            raise RuntimeError("Kubernetes apps client not initialized")
        deployment = apps_v1.read_namespaced_deployment(name=deploy, namespace=namespace)
        
        # Get requests from the first container in the pod template
        container = deployment.spec.template.spec.containers[0]
        replicas = deployment.spec.replicas or 0
        
        if not container.resources or not container.resources.requests:
            # No requests set
            return {"cpu": "0", "memory": "0", "replicas": replicas}
            
        requests = container.resources.requests
        
        # Return values, using "0" as a default if a key is missing
        return {
            "cpu": requests.get("cpu", "0"),
            "memory": requests.get("memory", "0"),
            "replicas": replicas
        }

    except Exception as e:
        print(f"Error reading deployment '{deploy}': {e}")
        # Return a "safe" empty state
        return {"cpu": "0", "memory": "0", "replicas": 0}
