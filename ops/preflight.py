from kubernetes import client, config
from kubernetes.client.rest import ApiException

SIM_GROUP = "simkube.io"
SIM_PLURAL = "simulations"
TARGET_NAMESPACE = "test-ns"
MIN_KUBECTL_VERSION = "1.20.0"

def check_kube_api() -> bool:
    print("Checking Kubernetes API connectivity...")
    try:
        config.load_kube_config()
        v1 = client.CoreV1Api() # 
        v1.get_api_resources()
        print("Kubernetes API is reachable")
        return True
    except Exception as e:
        print(f"X Failed to connect to Kubernetes API: {e}")
        return False


def check_namespace(namespace: str) -> bool:
    print(f"Checking namespace '{namespace}'...")
    try:
        v1 = client.CoreV1Api()
        v1.read_namespace(namespace)
        print(f"Namespace '{namespace}' exists")
        return True
    except ApiException as e:
        if e.status == 404:
            print(f"X Namespace '{namespace}' not found")
            print(f"  Create it with: kubectl create namespace {namespace}")
        else:
            print(f"X Error checking namespace: {e}")
        return False

def check_crd() -> bool:
    crd_name = f"{SIM_PLURAL}.{SIM_GROUP}"
    print(f"Checking for CRD '{crd_name}'...")
    try:
        apix = client.ApiextensionsV1Api()
        apix.read_custom_resource_definition(crd_name)
        print(f"✓ CRD '{crd_name}' is installed")
        return True

def main():
    check_kube_api()
    print("-"*20)
    check_namespace(TARGET_NAMESPACE)