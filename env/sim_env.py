# env/sim_env.py
import time
from kubernetes import client, config
from kubernetes.client.rest import ApiException

# TODO: confirm these on your cluster:
# kubectl api-resources --api-group=<group> -o wide
# kubectl get crd simulations.<group> -o yaml
SIM_GROUP = "simkube.io"       # Updated to match SimKube docs
SIM_VER = "v1"                 # Updated to match SimKube docs
SIM_PLURAL = "simulations"

class SimEnv:
    def __init__(self):
        # Use ~/.kube/config if present; otherwise assume we're running in-cluster.
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()
        #TODO get cluster context name based on the name passed in during isengard just run simkube cluster-name = [];  kind-[cluster-name]
        

        self.custom = client.CustomObjectsApi() # read/write CRDs (eg Simulation)
        self.core = client.CoreV1Api() # read/write core objects (eg ConfigMap)
        self.apix = client.ApiextensionsV1Api() # check CRD exist

    def _crd_installed(self) -> bool:
        # Fast, explicit check so we only fall back when the CRD truly isn't there.
        crd_name = f"{SIM_PLURAL}.{SIM_GROUP}"
        try:
            self.apix.read_custom_resource_definition(crd_name)
            return True
        except ApiException as e:
            if e.status == 404:
                return False
            # Any other error should propagate; don't silently fall back.
            raise

    def create(self, name, trace_path, namespace, duration_s,
               driver_image: str = "quay.io/appliedcomputing/sk-driver:v2.4.2", 
               driver_port: int = 8888):
        """
        Try to create a Simulation CR; if the CRD is missing, create a ConfigMap as a harmless placeholder.

        Parameters:
        name: the Kubernetes object name (must be DNS-1123 compliant).
        trace_path: where the driver finds the trace (as the Simulation spec expects).
        namespace: target namespace.
        duration_s: step window (seconds).
        driver_image, driver_port: defaults for SimKubes driver fields in the Simulation spec.
        """
        if self._crd_installed():
            # Simulation CRD is cluster-scoped, so don't include namespace in metadata
            # body = {
            #     "apiVersion": f"{SIM_GROUP}/{SIM_VER}",
            #     "kind": "Simulation",
            #     "metadata": {"name": name},  # Cluster-scoped: no namespace in metadata
            #     "spec": {
            #         "driver": {
            #             "image": driver_image,
            #             "namespace": namespace,  # Driver runs in this namespace
            #             "port": int(driver_port),
            #             "tracePath": trace_path,
            #         },
            #         "duration": f"{int(duration_s)}s",
            #     },
            # }
            body = {
                "apiVersion": f"{SIM_GROUP}/{SIM_VER}",
                "kind": "Simulation",
                "metadata": {"name": name},  # Cluster-scoped: no namespace in metadata
                "spec": {
                    "driver": {
                        "image": driver_image,
                        "namespace": "simkube",  # Driver always runs in simkube namespace (has secrets/SA)
                        "port": int(driver_port),
                        "tracePath": trace_path,
                        "virtualNsPrefix": "virtual",  # Pods created in virtual-<namespace>
                    },
                    "hooks": {
                          "preStartHooks": [{
                            "args": [
                                "apply",
                                "-f",
                                "/config/kwok"
                            ],
                            "cmd": "kubectl"
                        }]
                    },
                    "duration": f"{int(duration_s)}s",
                },
            }
            try:
                # Use cluster-scoped API for cluster-scoped CRD
                self.custom.create_cluster_custom_object(
                    group=SIM_GROUP, version=SIM_VER,
                    plural=SIM_PLURAL, body=body
                )
                return {"kind": "simulation", "name": name, "ns": namespace}
            except ApiException as e:
                if e.status == 409:
                    # Already exists; treat as success so delete() can clean it.
                    return {"kind": "simulation", "name": name, "ns": namespace}
                raise  # real error—surface it

        # Fallback: prove create→wait→delete wiring without the CRD
        cm = client.V1ConfigMap(
            metadata=client.V1ObjectMeta(name=name, namespace=namespace),
            data={"tracePath": str(trace_path), "duration": str(int(duration_s))}
        )
        self.core.create_namespaced_config_map(namespace=namespace, body=cm)
        return {"kind": "configmap", "name": name, "ns": namespace}

    def wait_fixed(self, seconds: int):
        time.sleep(int(seconds))

    def delete(self, handle=None, name=None, namespace=None):
        """
        Delete whatever we created in create(). Ignore 404s to be idempotent.
        
        Can be called with either:
        - handle dict: {"kind": "simulation", "name": "...", "ns": "..."}
        - name and namespace: delete(name="...", namespace="...")
        """
        # Extract name and namespace from handle if provided
        if handle:
            name = handle.get("name")
            namespace = handle.get("ns") or handle.get("namespace")
            kind = handle.get("kind")
        elif not (name and namespace):
            raise ValueError("Must provide either handle dict or name+namespace")
        else:
            kind = None  # Unknown, will try both
        
        # If we know the kind from handle, use it; otherwise try both
        if kind == "simulation":
            # Try simulation only (cluster-scoped, so no namespace parameter)
            try:
                self.custom.delete_cluster_custom_object(
                    group=SIM_GROUP, version=SIM_VER,
                    plural=SIM_PLURAL, name=name,
                    body=client.V1DeleteOptions(propagation_policy="Foreground",
                                                grace_period_seconds=0)
                )
            except ApiException as e:
                if e.status != 404:
                    raise
        elif kind == "configmap":
            # Try configmap only
            try:
                self.core.delete_namespaced_config_map(
                    name=name, namespace=namespace,
                    body=client.V1DeleteOptions()
                )
            except ApiException as e:
                if e.status != 404:
                    raise
        else:
            # Unknown kind - try simulation first, then configmap
            # Try simulation (cluster-scoped, so no namespace parameter)
            try:
                self.custom.delete_cluster_custom_object(
                    group=SIM_GROUP, version=SIM_VER,
                    plural=SIM_PLURAL, name=name,
                    body=client.V1DeleteOptions(propagation_policy="Foreground",
                                                grace_period_seconds=0)
                )
                return  # Success
            except ApiException as e:
                if e.status != 404:
                    raise
            
            # Try configmap
            try:
                self.core.delete_namespaced_config_map(
                    name=name, namespace=namespace,
                    body=client.V1DeleteOptions()
                )
            except ApiException as e:
                if e.status != 404:
                    raise
                # Both failed with 404, that's okay (idempotent)
