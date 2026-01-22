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
        print("  Ensure your kubeconfig is properly configured")
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
    except ApiException as e:
        if e.status == 404:
            print(f"X CRD '{crd_name}' not found")
            print(f"  Install it with: kubectl apply -f <crd-manifest>")
        else:
            print(f"X Error checking CRD: {e}")
        return False
    except Exception as e:
        print(f"X Error checking CRD: {e}")
        return False


def parse_version(version_str: str) -> tuple:
    """Parse version string like 'v1.20.0' or '1.20.0' into tuple of ints."""
    version_str = version_str.lstrip('v')
    try:
        parts = version_str.split('.')
        return tuple(int(p) for p in parts[:3])
    except (ValueError, IndexError):
        return (0, 0, 0)


def check_kubectl() -> bool:
    """Check if kubectl is available and meets minimum version."""
    print("Checking kubectl availability...")
    try:
        result = subprocess.run(
            ["kubectl", "version", "--client", "--short"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            # Try alternate format for newer kubectl versions
            result = subprocess.run(
                ["kubectl", "version", "--client", "-o", "json"],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode != 0:
                print(f"X kubectl command failed: {result.stderr}")
                return False
        
        # Parse version from output
        output = result.stdout.strip()
        # Extract version number from various output formats
        version_str = "unknown"
        for line in output.split('\n'):
            if 'version' in line.lower() or 'gitVersion' in line:
                parts = line.split()
                for part in parts:
                    if part.startswith('v') or '.' in part:
                        version_str = part.strip('",')
                        break
                if version_str != "unknown":
                    break
        
        current_version = parse_version(version_str)
        min_version = parse_version(MIN_KUBECTL_VERSION)
        
        if current_version >= min_version:
            print(f"✓ kubectl is available (version {version_str})")
            return True
        else:
            print(f"X kubectl version {version_str} is below minimum {MIN_KUBECTL_VERSION}")
            return False
            
    except FileNotFoundError:
        print("X kubectl not found in PATH")
        print("  Install kubectl: https://kubernetes.io/docs/tasks/tools/")
        return False
    except subprocess.TimeoutExpired:
        print("X kubectl command timed out")
        return False
    except Exception as e:
        print(f"X Error checking kubectl: {e}")
        return False


def main():
    print("-" * 30)
    print("SimKube Agent Preflight Checks")
    print("-" * 30)
    print()
    
    checks = [
        ("Kubernetes API", check_kube_api),
        ("Target Namespace", lambda: check_namespace(TARGET_NAMESPACE)),
        ("SimKube CRD", check_crd),
        ("kubectl", check_kubectl),
    ]
    
    results = []
    for name, check_fn in checks:
        try:
            results.append(check_fn())
        except Exception as e:
            print(f"X Unexpected error in {name} check: {e}")
            results.append(False)
        print()

    print("-" * 30)
    passed = sum(results)
    total = len(results)
    
    if all(results):
        print(f"All {total} checks passed")
        print("-" * 30)
        return 0
    else:
        print(f"{passed}/{total} checks passed")
        print("-" * 30)
        return 1

if __name__ == "__main__":
    import sys
    sys.exit(main())