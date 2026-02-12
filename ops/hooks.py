#!/usr/bin/env python3

import logging
import time
from typing import Literal, List, Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

HookStage = Literal["pre_start", "pre_run", "post_run", "post_stop"]

logger = logging.getLogger("hooks")

# Wait for deletion to complete before starting next simulation (avoids race condition)
WAIT_FOR_DELETION_TIMEOUT_S = 90
WAIT_FOR_DELETION_POLL_INTERVAL_S = 2


def wait_for_pods_terminated(namespace: str, timeout_s: int = WAIT_FOR_DELETION_TIMEOUT_S) -> bool:
    """
    Poll until no pods remain in the namespace. Prevents race between pod deletion
    and SimKube starting the next simulation (per SimKube maintainer recommendation).
    Returns True if namespace is empty, False if timeout.
    """
    core = client.CoreV1Api()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            pod_list = core.list_namespaced_pod(namespace=namespace, limit=10)
            if not pod_list.items:
                return True
        except ApiException as e:
            if e.status == 404:
                return True  # Namespace doesn't exist, consider it clean
            raise
        time.sleep(WAIT_FOR_DELETION_POLL_INTERVAL_S)
    return False


def wait_for_deployment_deleted(namespace: str, deploy: str, timeout_s: int = WAIT_FOR_DELETION_TIMEOUT_S) -> bool:
    """
    Poll until the deployment no longer exists. Ensures SimKube's cleanup from
    the previous simulation is complete before starting the next one (fixes step 5 404).
    Returns True if deployment is gone, False if timeout.
    """
    apps = client.AppsV1Api()
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        try:
            apps.read_namespaced_deployment(name=deploy, namespace=namespace)
            # Deployment exists, keep waiting
        except ApiException as e:
            if e.status == 404:
                return True  # Deployment gone
            raise
        time.sleep(WAIT_FOR_DELETION_POLL_INTERVAL_S)
    return False


class LocalHooks:
    """
    Local cleanup operations that run on the agent host machine.
    These are NOT SimKube hooks - they run before/after the agent creates simulations.
    """
    
    def __init__(self):
        try:
            config.load_kube_config()
        except Exception:
            config.load_incluster_config()
        
        self.core = client.CoreV1Api()
        self.custom = client.CustomObjectsApi()
    
    def delete_all_pods(self, namespace: str) -> int:
        """
        Delete all pods in the given namespace.       
        Args:       namespace: Target namespace
        Returns:    Number of pods deleted
        """

        logger.debug(f"Deleting pods in namespace '{namespace}'...")   
        try:
            # List pods
            pod_list = self.core.list_namespaced_pod(namespace=namespace, limit=100)
            
            if not pod_list.items:
                logger.debug(f"No pods found in namespace '{namespace}' (already clean)")
                return 0
            
            # Delete each pod
            deleted_count = 0
            for pod in pod_list.items:
                pod_name = pod.metadata.name
                try:
                    self.core.delete_namespaced_pod(
                        name=pod_name,
                        namespace=namespace,
                        body=client.V1DeleteOptions(
                            grace_period_seconds=0,
                            propagation_policy="Foreground"
                        )
                    )
                    deleted_count += 1
                    logger.debug(f". Deleted pod: {pod_name}")
                except ApiException as e:
                    if e.status == 404:
                        logger.debug(f"  • Pod {pod_name} already deleted")
                    else:
                        logger.warning(f"  X Warning: Failed to delete pod {pod_name}: {e}")
            
            logger.info(f"Deleted {deleted_count} pod(s) from namespace '{namespace}'")
            return deleted_count
            
        except ApiException as e:
            if e.status == 404:
                logger.debug(f"Namespace '{namespace}' not found (nothing to clean)")
                return 0
            else:
                raise
    
    def pre_start(self, namespace: str, deploy: Optional[str] = None) -> None:
        """
        Pre-start hook: Clean environment before agent episode.
        This runs on your machine BEFORE creating a Simulation CR.
        Waits for pod deletion and (optionally) deployment deletion to complete
        to avoid race with SimKube (multi-step fix).
        """
        logger.debug(f"=== pre_start hook for namespace '{namespace}' ===")
        self.delete_all_pods(namespace)
        logger.debug("Waiting for Kubernetes to complete pod deletion (avoids race with SimKube)...")
        if wait_for_pods_terminated(namespace):
            logger.debug("Pods terminated.")
        else:
            logger.warning("Timeout waiting for pods to terminate, proceeding anyway.")
        if deploy:
            logger.debug(f"Waiting for deployment '{deploy}' to be fully cleaned up...")
            if wait_for_deployment_deleted(namespace, deploy):
                logger.debug("Deployment cleanup complete.")
            else:
                logger.warning("Timeout waiting for deployment to be deleted, proceeding anyway.")
        logger.debug("pre_start hook completed")


def run_hooks(stage: HookStage, namespace: str, deploy: Optional[str] = None) -> None:
    """
    Wrapper function for runner/one_step.py.
    Creates a LocalHooks instance and calls the appropriate method based on stage.
    deploy: used in pre_start to wait for previous deployment cleanup (multi-step fix).
    """
    hooks = LocalHooks()
    if stage == "pre_start":
        hooks.pre_start(namespace, deploy=deploy)
    elif stage == "pre_run":
        # Future: implement pre_run
        pass
    elif stage == "post_run":
        # Future: implement post_run
        pass
    elif stage == "post_stop":
        # Future: implement post_stop
        pass
    else:
        raise ValueError(f"Unknown hook stage: {stage}")
