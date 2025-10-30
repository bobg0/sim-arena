# observe/reader.py
from kubernetes import client, config

# Load kubeconfig from ~/.kube/config
config.load_kube_config()

# Create API clients
v1 = client.CoreV1Api()
apps_v1 = client.AppsV1Api()

def observe(namespace: str, deployment_name: str) -> dict:
    """
    Observes a specific deployment in a namespace and returns pod counts.
    
    NOTE: This assumes the deployment's pods are findable using a 
    label selector 'app: <deployment_name>'
    """
    
    # This label selector is an assumption, but a very common one.
    # It's the key to linking pods to the 'web' deployment.
    label_selector = f"app={deployment_name}"
    
    try:
        # List all pods in the namespace that match the label
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

    except client.ApiException as e:
        print(f"Error observing pods: {e}")
        # On error, return a "safe" empty/zero state
        return {"ready": 0, "pending": 0, "total": 0}

def current_requests(namespace: str, deploy: str) -> dict:
    """
    Gets the *current* CPU/Memory requests for a deployment's first container.
    """
    try:
        deployment = apps_v1.read_namespaced_deployment(name=deploy, namespace=namespace)
        
        # Get requests from the first container in the pod template
        container = deployment.spec.template.spec.containers[0]
        
        if not container.resources or not container.resources.requests:
            # No requests set
            return {"cpu": "0", "memory": "0"}
            
        requests = container.resources.requests
        
        # Return values, using "0" as a default if a key is missing
        return {
            "cpu": requests.get("cpu", "0"),
            "memory": requests.get("memory", "0")
        }

    except client.ApiException as e:
        print(f"Error reading deployment '{deploy}': {e}")
        # Return a "safe" empty state
        return {"cpu": "0", "memory": "0"}
