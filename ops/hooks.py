#!/usr/bin/env python3

import logging
from typing import Literal, List, Dict, Any, Optional
from kubernetes import client, config
from kubernetes.client.rest import ApiException

HookStage = Literal["pre_start", "pre_run", "post_run", "post_stop"]

logger = logging.getLogger("hooks")

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
    
    def pre_start(self, namespace: str) -> None:
        """
        Pre-start hook: Clean environment before agent episode.
        This runs on your machine BEFORE creating a Simulation CR.
        """
        logger.debug(f"=== pre_start hook for namespace '{namespace}' ===")
        self.delete_all_pods(namespace)
        logger.debug("pre_start hook completed")


def run_hooks(stage: HookStage, namespace: str) -> None:
    """
    Wrapper function for runner/one_step.py.
    Creates a LocalHooks instance and calls the appropriate method based on stage.
    """
    hooks = LocalHooks()
    if stage == "pre_start":
        hooks.pre_start(namespace)
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