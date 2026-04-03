"""
<<<<<<< HEAD
Minimal terminal demo for the presentation MVP.

Story:
1. Replay an existing failing trace.
2. Show pods stuck Pending because CPU requests are too high.
3. Apply one CPU remediation using the existing trace op semantics.
4. Replay the fixed trace and verify the pods become Ready.

Run from the repo root after activating the venv:
    python -m runner.demo_mvp
=======
Recordable terminal demo for the MVP glue layer.

The demo uses a fixed synthetic trace and a short, planned action sequence:
1. Start from an unhealthy replay state.
2. Apply one action to improve memory pressure.
3. Apply one action to reduce excess replicas.
4. Apply one action to bump CPU.

Each action mutates the trace with the existing ops layer, replays it through
SimKube, and prints a compact state snapshot for recording.
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from kubernetes import client, config
from kubernetes.client.rest import ApiException


SCRIPT_DIR = Path(__file__).parent.absolute()
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

<<<<<<< HEAD
from env.actions.ops import reduce_cpu_small
from env.actions.trace_io import load_trace, save_trace
from env.sim_env import SimEnv
from observe.reader import current_requests, observe
from ops.hooks import run_hooks
from runner.safeguards import parse_cpu_to_millicores, validate_action


DEFAULT_TRACE = "demo/trace-cpu-slight.msgpack"
DEFAULT_NAMESPACE = "default"
=======
from env.actions.ops import bump_cpu_small, reduce_mem_small, scale_down_replicas
from env.actions.trace_io import load_trace, save_trace
from env.sim_env import SimEnv
from ops.hooks import LocalHooks, wait_for_deployment_deleted, wait_for_pods_terminated
from runner.safeguards import validate_action


DEFAULT_TRACE = "demo/trace-cpu-low-mem-high-replicas-over.msgpack"
DEFAULT_NAMESPACE = "simkube"
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
DEFAULT_VIRTUAL_NAMESPACE = "virtual-default"
DEFAULT_DEPLOYMENT = "web"
DEFAULT_TARGET_READY = 3
DEFAULT_DURATION_S = 18
<<<<<<< HEAD
DEFAULT_TARGET_CPU = "16000m"
DEFAULT_POLL_TIMEOUT_S = 20
POLL_INTERVAL_S = 2
=======
DEFAULT_DRIVER_TIMEOUT_S = 45
DEFAULT_DEPLOY_TIMEOUT_S = 45
DEFAULT_POLL_TIMEOUT_S = 24
DEFAULT_CLEANUP_TIMEOUT_S = 10
POLL_INTERVAL_S = 2
VISIBLE_NODE_NAMES = {"node1", "node2", "node3"}
KWOK_STAGE_NAME = "sim-arena-pod-ready"

PLANNED_ACTIONS = [
    {
        "type": "reduce_mem_small",
        "step": "32.5Gi",
        "summary": "memory 33Gi -> 512Mi",
        "focus": "memory",
    },
    {
        "type": "scale_down_replicas",
        "delta": 2,
        "summary": "replicas 5 -> 3",
        "focus": "replicas",
    },
    {
        "type": "bump_cpu_small",
        "step": "250m",
        "summary": "cpu 250m -> 500m",
        "focus": "cpu",
    },
]
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


@dataclass
class Snapshot:
    obs: dict[str, Any]
    resources: dict[str, Any]
    pods: list[dict[str, str]]


def _print_banner(title: str) -> None:
    print()
    print(title)
    print("=" * len(title))


def _print_kv(label: str, value: str) -> None:
    print(f"{label:<14} {value}")


def _get_node_data_dir() -> Path:
    override = os.environ.get("SIM_ARENA_NODE_DATA_DIR")
    if override:
        return Path(override)

    cluster_name = os.environ.get("SIM_ARENA_KIND_CLUSTER")
    if not cluster_name:
        try:
            _, active = config.list_kube_config_contexts()
            active_name = (active or {}).get("name", "")
        except Exception:
            active_name = ""
<<<<<<< HEAD
        if active_name.startswith("kind-"):
            cluster_name = active_name.removeprefix("kind-")
        else:
            cluster_name = "cluster"
=======
        cluster_name = active_name.removeprefix("kind-") if active_name.startswith("kind-") else "cluster"
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d

    return Path.home() / ".local" / "kind-node-data" / cluster_name


<<<<<<< HEAD
def _extract_trace_state(trace_path: str, deploy: str) -> dict[str, Any]:
    trace = load_trace(trace_path)
    current_state = {"cpu": "0m", "memory": "0Mi", "replicas": 0}

    for event in trace.get("events", []):
=======
def _load_clients() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return client.CoreV1Api(), client.AppsV1Api()


def _load_api_clients() -> tuple[client.CoreV1Api, client.AppsV1Api, client.BatchV1Api, client.CustomObjectsApi]:
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return (
        client.CoreV1Api(),
        client.AppsV1Api(),
        client.BatchV1Api(),
        client.CustomObjectsApi(),
    )


def _kwok_pod_ready_stage_body(virtual_namespace: str, deploy: str) -> dict[str, Any]:
    return {
        "apiVersion": "kwok.x-k8s.io/v1alpha1",
        "kind": "Stage",
        "metadata": {"name": KWOK_STAGE_NAME},
        "spec": {
            "immediateNextStage": True,
            "resourceRef": {
                "apiGroup": "v1",
                "kind": "Pod",
            },
            "selector": {
                "matchLabels": {"app": deploy},
                "matchExpressions": [
                    {
                        "key": ".metadata.namespace",
                        "operator": "In",
                        "values": [virtual_namespace],
                    },
                    {
                        "key": '.status.conditions.[] | select( .type == "PodScheduled" ) | .status',
                        "operator": "In",
                        "values": ["True"],
                    },
                ],
            },
            "next": {
                "event": {
                    "type": "Normal",
                    "reason": "KwokPodReady",
                    "message": "KWOK marked the pod ready",
                },
                "patches": [
                    {
                        "subresource": "status",
                        "type": "merge",
                        "template": (
                            "status:\n"
                            "  phase: Running\n"
                            "  conditions:\n"
                            "  - lastTransitionTime: {{ Now | Quote }}\n"
                            "    message: Pod is ready\n"
                            "    reason: KwokPodReady\n"
                            '    status: "True"\n'
                            "    type: Ready\n"
                        ),
                    }
                ],
            },
        },
    }


def _ensure_kwok_pod_ready_stage(virtual_namespace: str, deploy: str) -> None:
    _, _, _, custom = _load_api_clients()
    body = _kwok_pod_ready_stage_body(virtual_namespace, deploy)

    try:
        existing = custom.get_cluster_custom_object(
            "kwok.x-k8s.io",
            "v1alpha1",
            "stages",
            KWOK_STAGE_NAME,
        )
        body["metadata"]["resourceVersion"] = existing.get("metadata", {}).get("resourceVersion")
        custom.replace_cluster_custom_object(
            "kwok.x-k8s.io",
            "v1alpha1",
            "stages",
            KWOK_STAGE_NAME,
            body=body,
        )
    except ApiException as exc:
        if exc.status != 404:
            raise
        custom.create_cluster_custom_object(
            "kwok.x-k8s.io",
            "v1alpha1",
            "stages",
            body=body,
        )


def _prepare_trace_for_cluster(trace_path: str) -> str:
    source = Path(trace_path)
    if not source.exists():
        raise FileNotFoundError(f"Trace not found: {source}")

    node_data_dir = _get_node_data_dir()
    node_data_dir.mkdir(parents=True, exist_ok=True)
    destination = node_data_dir / source.name
    shutil.copy2(source, destination)
    return f"file:///data/{source.name}"


def _quick_cleanup(namespace: str, deploy: str, timeout_s: int) -> None:
    hooks = LocalHooks()
    hooks.delete_all_pods(namespace)
    wait_for_pods_terminated(namespace, timeout_s=timeout_s)
    wait_for_deployment_deleted(namespace, deploy, timeout_s=timeout_s)


def _force_cleanup_simulation(sim_name: str, virtual_namespace: str, deploy: str) -> None:
    core, apps, batch, custom = _load_api_clients()
    delete_now = client.V1DeleteOptions(grace_period_seconds=0, propagation_policy="Foreground")

    try:
        batch.delete_namespaced_job(
            name=f"sk-{sim_name}-driver",
            namespace="simkube",
            body=delete_now,
        )
    except ApiException as exc:
        if exc.status != 404:
            raise

    try:
        apps.delete_namespaced_deployment(
            name=deploy,
            namespace=virtual_namespace,
            body=delete_now,
        )
    except ApiException as exc:
        if exc.status != 404:
            raise

    try:
        pod_list = core.list_namespaced_pod(namespace=virtual_namespace, label_selector=f"app={deploy}")
        for pod in pod_list.items:
            core.delete_namespaced_pod(
                name=pod.metadata.name,
                namespace=virtual_namespace,
                body=delete_now,
            )
    except ApiException as exc:
        if exc.status != 404:
            raise

    roots = custom.list_cluster_custom_object("simkube.io", "v1", "simulationroots")
    for item in roots.get("items", []):
        labels = item.get("metadata", {}).get("labels", {}) or {}
        if labels.get("simkube.io/simulation") != sim_name:
            continue
        root_name = item.get("metadata", {}).get("name")
        if not root_name:
            continue
        try:
            custom.delete_cluster_custom_object(
                "simkube.io",
                "v1",
                "simulationroots",
                root_name,
                body=delete_now,
            )
        except ApiException as exc:
            if exc.status != 404:
                raise

    try:
        custom.delete_cluster_custom_object(
            "simkube.io",
            "v1",
            "simulations",
            sim_name,
            body=delete_now,
        )
    except ApiException as exc:
        if exc.status != 404:
            raise


def _wait_for_no_active_simulations(timeout_s: int) -> None:
    _, _, _, custom = _load_api_clients()
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        sims = custom.list_cluster_custom_object("simkube.io", "v1", "simulations")
        items = sims.get("items", [])
        if not items:
            return
        time.sleep(POLL_INTERVAL_S)

    names = [item.get("metadata", {}).get("name", "<unknown>") for item in items]
    raise RuntimeError(f"previous SimKube simulations are still active: {', '.join(names)}")


def _wait_for_simulation_deleted(sim_name: str, timeout_s: int) -> None:
    _, _, _, custom = _load_api_clients()
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            custom.get_cluster_custom_object("simkube.io", "v1", "simulations", sim_name)
        except ApiException as exc:
            if exc.status == 404:
                return
            raise
        time.sleep(POLL_INTERVAL_S)
    raise RuntimeError(f"simulation '{sim_name}' did not finish deleting")


def _extract_trace_state(trace_obj: dict[str, Any], deploy: str) -> dict[str, Any]:
    current_state = {"cpu": "0m", "memory": "0Mi", "replicas": 0}

    for event in trace_obj.get("events", []):
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        for obj in event.get("applied_objs", []):
            if obj.get("kind") != "Deployment":
                continue
            if obj.get("metadata", {}).get("name") != deploy:
                continue

            spec = obj.get("spec", {})
            containers = spec.get("template", {}).get("spec", {}).get("containers", [])
            current_state["replicas"] = spec.get("replicas", 0)
            if containers:
                requests = containers[0].get("resources", {}).get("requests", {})
                current_state["cpu"] = requests.get("cpu", "0m")
                current_state["memory"] = requests.get("memory", "0Mi")
            return current_state

<<<<<<< HEAD
    raise ValueError(f"Deployment '{deploy}' not found in trace: {trace_path}")


def _build_cpu_fix_trace(
    trace_path: str,
    deploy: str,
    target_cpu: str,
    output_path: str,
) -> tuple[str, dict[str, str]]:
    trace = load_trace(trace_path)
    current_state = _extract_trace_state(trace_path, deploy)
    current_cpu = str(current_state["cpu"])
    current_m = parse_cpu_to_millicores(current_cpu)
    target_m = parse_cpu_to_millicores(target_cpu)

    if target_m >= current_m:
        raise ValueError(
            f"Target CPU {target_cpu} must be lower than current trace CPU {current_cpu} "
            "for the existing reduce_cpu_small remediation."
        )

    step = f"{current_m - target_m}m"
    action = {"type": "reduce_cpu_small", "step": step}
    is_valid, error = validate_action(action, current_state=current_state)
    if not is_valid:
        raise ValueError(error or "CPU remediation action was rejected by safeguards")

    changed = reduce_cpu_small(trace, deploy, step=step)
    if not changed:
        raise RuntimeError("reduce_cpu_small did not modify the trace")

    save_trace(trace, output_path)
    return output_path, {"from_cpu": current_cpu, "to_cpu": target_cpu, "step": step}


def _load_clients() -> tuple[client.CoreV1Api, client.AppsV1Api]:
    try:
        config.load_kube_config()
    except Exception:
        config.load_incluster_config()
    return client.CoreV1Api(), client.AppsV1Api()
=======
    raise ValueError(f"Deployment '{deploy}' not found in trace")


def _apply_action_to_trace(trace_path: str, deploy: str, action: dict[str, Any], output_path: str) -> str:
    trace = load_trace(trace_path)
    current_state = _extract_trace_state(trace, deploy)
    is_valid, error = validate_action(action, current_state=current_state)
    if not is_valid:
        raise ValueError(error or f"Action rejected: {action}")

    action_type = action["type"]
    if action_type == "reduce_mem_small":
        changed = reduce_mem_small(trace, deploy, step=action["step"])
    elif action_type == "scale_down_replicas":
        changed = scale_down_replicas(trace, deploy, delta=action["delta"])
    elif action_type == "bump_cpu_small":
        changed = bump_cpu_small(trace, deploy, step=action["step"])
    else:
        raise ValueError(f"Unsupported action type for demo: {action_type}")

    if not changed:
        raise RuntimeError(f"Action did not modify the trace: {action}")

    save_trace(trace, output_path)
    return output_path
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


def _list_pods(core: client.CoreV1Api, namespace: str, deploy: str) -> list[dict[str, str]]:
    pod_list = core.list_namespaced_pod(namespace=namespace, label_selector=f"app={deploy}")
    rows: list[dict[str, str]] = []

    for pod in sorted(pod_list.items, key=lambda item: item.metadata.name or ""):
        ready_count = 0
        total_count = 0
        reason = pod.status.reason or ""
<<<<<<< HEAD
=======
        condition_ready = False
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d

        for status in pod.status.container_statuses or []:
            total_count += 1
            if status.ready:
                ready_count += 1
            if not reason and status.state and status.state.waiting:
                reason = status.state.waiting.reason or ""

        if not reason and pod.status.conditions:
            for condition in pod.status.conditions:
<<<<<<< HEAD
=======
                if condition.type == "Ready" and condition.status == "True":
                    condition_ready = True
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
                if condition.type == "PodScheduled" and condition.status == "False":
                    reason = condition.reason or ""
                    break

<<<<<<< HEAD
=======
        if total_count == 0 and condition_ready:
            ready_count = 1
            total_count = 1

        node_name = pod.spec.node_name or "-"
        display_node = node_name if node_name in VISIBLE_NODE_NAMES else "-"

>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        rows.append(
            {
                "name": pod.metadata.name or "<unknown>",
                "phase": pod.status.phase or "Unknown",
                "ready": f"{ready_count}/{total_count or 1}",
                "reason": reason or "-",
<<<<<<< HEAD
=======
                "node": display_node,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
            }
        )

    return rows


<<<<<<< HEAD
def _snapshot(core: client.CoreV1Api, namespace: str, deploy: str) -> Snapshot:
    return Snapshot(
        obs=observe(namespace, deploy),
        resources=current_requests(namespace, deploy),
        pods=_list_pods(core, namespace, deploy),
    )


def _wait_for_driver(core: client.CoreV1Api, sim_name: str, timeout_s: int) -> None:
=======
def _deployment_resources(apps: client.AppsV1Api, namespace: str, deploy: str) -> dict[str, Any]:
    try:
        deployment = apps.read_namespaced_deployment(name=deploy, namespace=namespace)
    except ApiException as exc:
        if exc.status == 404:
            return {"cpu": "0", "memory": "0", "replicas": 0}
        raise

    container = deployment.spec.template.spec.containers[0]
    replicas = deployment.spec.replicas or 0
    requests = getattr(container.resources, "requests", None) or {}
    return {
        "cpu": requests.get("cpu", "0"),
        "memory": requests.get("memory", "0"),
        "replicas": replicas,
    }


def _pod_observation(pods: list[dict[str, str]]) -> dict[str, int]:
    total = len(pods)
    pending = sum(1 for pod in pods if pod["phase"] == "Pending")
    ready = sum(1 for pod in pods if pod["ready"].startswith("1/") and pod["phase"] == "Running")
    assigned = sum(1 for pod in pods if pod["node"] != "-")
    unschedulable = sum(1 for pod in pods if pod["reason"] == "Unschedulable")
    return {
        "ready": ready,
        "pending": pending,
        "total": total,
        "assigned": assigned,
        "unschedulable": unschedulable,
    }


def _snapshot(core: client.CoreV1Api, apps: client.AppsV1Api, namespace: str, deploy: str) -> Snapshot:
    pods = _list_pods(core, namespace, deploy)
    return Snapshot(
        obs=_pod_observation(pods),
        resources=_deployment_resources(apps, namespace, deploy),
        pods=pods,
    )


def _wait_for_driver(core: client.CoreV1Api, sim_name: str, timeout_s: int) -> bool:
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    deadline = time.time() + timeout_s
    label_selector = f"job-name=sk-{sim_name}-driver"

    while time.time() < deadline:
        pods = core.list_pod_for_all_namespaces(label_selector=label_selector).items
        if pods:
            phase = pods[0].status.phase or ""
<<<<<<< HEAD
            if phase in {"Running", "Succeeded"}:
                return
            if phase == "Failed":
                raise RuntimeError(f"driver pod failed for simulation {sim_name}")
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(f"driver pod did not become ready within {timeout_s}s")


def _wait_for_deployment(apps: client.AppsV1Api, namespace: str, deploy: str, timeout_s: int) -> None:
=======
            if phase in {"Running", "Succeeded", "Failed"}:
                return True
        time.sleep(POLL_INTERVAL_S)

    return False


def _wait_for_deployment(apps: client.AppsV1Api, namespace: str, deploy: str, timeout_s: int) -> bool:
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            apps.read_namespaced_deployment(name=deploy, namespace=namespace)
<<<<<<< HEAD
            return
=======
            return True
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        except ApiException as exc:
            if exc.status != 404:
                raise
        time.sleep(POLL_INTERVAL_S)

<<<<<<< HEAD
    raise TimeoutError(f"deployment/{deploy} did not appear in {namespace} within {timeout_s}s")
=======
    return False
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


def _wait_for_snapshot(
    core: client.CoreV1Api,
<<<<<<< HEAD
=======
    apps: client.AppsV1Api,
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    namespace: str,
    deploy: str,
    timeout_s: int,
    success_predicate,
) -> Snapshot:
    deadline = time.time() + timeout_s
<<<<<<< HEAD
    last = _snapshot(core, namespace, deploy)

    while time.time() < deadline:
        last = _snapshot(core, namespace, deploy)
=======
    last = _snapshot(core, apps, namespace, deploy)

    while time.time() < deadline:
        last = _snapshot(core, apps, namespace, deploy)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        if success_predicate(last):
            return last
        time.sleep(POLL_INTERVAL_S)

    return last


<<<<<<< HEAD
def _format_snapshot(title: str, snapshot: Snapshot, target_ready: int) -> None:
    _print_banner(title)
    total = int(snapshot.obs.get("total", 0))
    ready = int(snapshot.obs.get("ready", 0))
    pending = int(snapshot.obs.get("pending", 0))
    replicas = snapshot.resources.get("replicas", total)

    _print_kv("pods", f"{total} total | {ready} ready | {pending} pending")
    _print_kv("desired", f"{replicas} replicas | target ready {target_ready}")
    _print_kv(
        "requests",
        f"cpu {snapshot.resources.get('cpu', '0')} | memory {snapshot.resources.get('memory', '0')}",
    )

    if not snapshot.pods:
        print("pod details     none observed")
        return

    print("pod details")
    print(f"{'NAME':<36} {'PHASE':<10} {'READY':<7} REASON")
    for pod in snapshot.pods[:6]:
        print(f"{pod['name']:<36} {pod['phase']:<10} {pod['ready']:<7} {pod['reason']}")


def _recovery_succeeded(before: Snapshot, after: Snapshot, target_ready: int) -> bool:
    desired_after = int(after.resources.get("replicas", after.obs.get("total", 0)))
    before_unhealthy = int(before.obs.get("pending", 0)) > 0 or int(before.obs.get("ready", 0)) < target_ready
    after_healthy = (
        int(after.obs.get("pending", 0)) == 0
        and int(after.obs.get("ready", 0)) == target_ready
        and desired_after == target_ready
    )
    improved = (
        int(after.obs.get("ready", 0)) > int(before.obs.get("ready", 0))
        or int(after.obs.get("pending", 0)) < int(before.obs.get("pending", 0))
    )
    return before_unhealthy and after_healthy and improved


def _prepare_trace_for_cluster(trace_path: str) -> str:
    source = Path(trace_path)
    if not source.exists():
        raise FileNotFoundError(f"Trace not found: {source}")

    node_data_dir = _get_node_data_dir()
    node_data_dir.mkdir(parents=True, exist_ok=True)
    destination = node_data_dir / source.name
    shutil.copy2(source, destination)
    return f"file:///data/{source.name}"


=======
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
def _run_replay(
    sim_env: SimEnv,
    core: client.CoreV1Api,
    apps: client.AppsV1Api,
    trace_path: str,
    namespace: str,
    virtual_namespace: str,
    deploy: str,
    duration_s: int,
<<<<<<< HEAD
    snapshot_timeout_s: int,
    snapshot_predicate,
) -> Snapshot:
    sim_name = f"demo-mvp-{uuid.uuid4().hex[:8]}"
    run_hooks("pre_start", virtual_namespace, deploy=deploy)
=======
    driver_timeout_s: int,
    deploy_timeout_s: int,
    snapshot_timeout_s: int,
    cleanup_timeout_s: int,
    success_predicate,
) -> Snapshot:
    sim_name = f"demo-mvp-{uuid.uuid4().hex[:8]}"
    try:
        _wait_for_no_active_simulations(timeout_s=max(cleanup_timeout_s, 12))
    except RuntimeError:
        _, _, _, custom = _load_api_clients()
        sims = custom.list_cluster_custom_object("simkube.io", "v1", "simulations")
        for item in sims.get("items", []):
            stale_name = item.get("metadata", {}).get("name")
            if stale_name:
                _force_cleanup_simulation(stale_name, virtual_namespace, deploy)
        _wait_for_no_active_simulations(timeout_s=max(cleanup_timeout_s, 20))
    _quick_cleanup(virtual_namespace, deploy, timeout_s=cleanup_timeout_s)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    cluster_trace = _prepare_trace_for_cluster(trace_path)
    handle = sim_env.create(
        name=sim_name,
        trace_path=cluster_trace,
        namespace=namespace,
        duration_s=duration_s,
    )

    try:
<<<<<<< HEAD
        _wait_for_driver(core, sim_name, timeout_s=max(duration_s, snapshot_timeout_s))
        _wait_for_deployment(apps, virtual_namespace, deploy, timeout_s=max(duration_s, snapshot_timeout_s))
        return _wait_for_snapshot(
            core,
            virtual_namespace,
            deploy,
            timeout_s=snapshot_timeout_s,
            success_predicate=snapshot_predicate,
        )
    finally:
        sim_env.delete(handle=handle)
=======
        driver_seen = _wait_for_driver(core, sim_name, timeout_s=driver_timeout_s)
        deployment_seen = _wait_for_deployment(apps, virtual_namespace, deploy, timeout_s=deploy_timeout_s)
        if not driver_seen:
            raise RuntimeError(
                f"driver job for simulation '{sim_name}' did not appear; "
                f"check the Simulation namespace ({namespace}) and SimKube controller events"
            )
        if not deployment_seen:
            raise RuntimeError(
                f"deployment/{deploy} did not appear in {virtual_namespace} after the driver started"
            )
        snapshot = _wait_for_snapshot(
            core,
            apps,
            virtual_namespace,
            deploy,
            timeout_s=snapshot_timeout_s,
            success_predicate=success_predicate,
        )
        if not success_predicate(snapshot):
            raise RuntimeError(
                f"deployment/{deploy} in {virtual_namespace} did not reach the expected state "
                f"within {snapshot_timeout_s}s"
            )
        return snapshot
    finally:
        sim_env.delete(handle=handle)
        try:
            _wait_for_simulation_deleted(sim_name, timeout_s=max(cleanup_timeout_s, 20))
        except RuntimeError:
            _force_cleanup_simulation(sim_name, virtual_namespace, deploy)
            _wait_for_simulation_deleted(sim_name, timeout_s=max(cleanup_timeout_s, 20))


def _count_scheduled(pods: list[dict[str, str]]) -> int:
    return sum(1 for pod in pods if pod.get("node") not in (None, "", "-"))


def _count_unschedulable(pods: list[dict[str, str]]) -> int:
    return sum(1 for pod in pods if pod.get("reason") == "Unschedulable")


def _all_expected_pods_ready(snapshot: Snapshot) -> bool:
    desired = int(snapshot.resources.get("replicas", snapshot.obs.get("total", 0)))
    ready = int(snapshot.obs.get("ready", 0))
    pending = int(snapshot.obs.get("pending", 0))
    total = int(snapshot.obs.get("total", 0))
    return desired > 0 and total == desired and ready == desired and pending == 0


def _format_step(step_idx: int, total_steps: int, label: str, snapshot: Snapshot, target_ready: int) -> None:
    _print_banner(f"Step {step_idx}/{total_steps}")
    _print_kv("label", label)
    total = int(snapshot.obs.get("total", 0))
    ready = int(snapshot.obs.get("ready", 0))
    pending = int(snapshot.obs.get("pending", 0))
    scheduled = int(snapshot.obs.get("assigned", _count_scheduled(snapshot.pods)))
    unschedulable = int(snapshot.obs.get("unschedulable", _count_unschedulable(snapshot.pods)))
    replicas = snapshot.resources.get("replicas", total)

    _print_kv("pods", f"{total} total | {ready} ready | {pending} pending")
    _print_kv("scheduled", f"{scheduled} on node1-3 | {unschedulable} unschedulable")
    _print_kv("desired", f"{replicas} replicas | target ready {target_ready}")
    _print_kv(
        "requests",
        f"cpu {snapshot.resources.get('cpu', '0')} | memory {snapshot.resources.get('memory', '0')}",
    )

    if snapshot.pods:
        print("pod details")
        print(f"{'NAME':<36} {'PHASE':<10} {'NODE':<10} {'READY':<7} REASON")
        for pod in snapshot.pods[:6]:
            print(f"{pod['name']:<36} {pod['phase']:<10} {pod['node']:<10} {pod['ready']:<7} {pod['reason']}")


def _final_success(snapshot: Snapshot, target_ready: int) -> bool:
    ready = int(snapshot.obs.get("ready", 0))
    desired = int(snapshot.resources.get("replicas", snapshot.obs.get("total", 0)))
    return ready == target_ready and int(snapshot.obs.get("pending", 0)) == 0 and desired == target_ready
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d


def run_demo(args: argparse.Namespace) -> int:
    trace_path = str(Path(args.trace))
    core, apps = _load_clients()
    sim_env = SimEnv()
<<<<<<< HEAD

    before_predicate = lambda snap: int(snap.obs.get("total", 0)) > 0
    after_predicate = lambda snap: (
        int(snap.obs.get("ready", 0)) == args.target
        and int(snap.obs.get("pending", 0)) == 0
    )

    fixed_trace_dir = Path(".tmp")
    fixed_trace_dir.mkdir(parents=True, exist_ok=True)
    fixed_trace_path = str(fixed_trace_dir / f"demo-mvp-fixed-{uuid.uuid4().hex[:8]}.msgpack")
    fixed_trace_path, cpu_change = _build_cpu_fix_trace(
        trace_path=trace_path,
        deploy=args.deploy,
        target_cpu=args.target_cpu,
        output_path=fixed_trace_path,
    )
=======
    _ensure_kwok_pod_ready_stage(args.virtual_namespace, args.deploy)
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d

    _print_banner("SimArena MVP Demo")
    _print_kv("trace", trace_path)
    _print_kv("namespace", args.virtual_namespace)
    _print_kv("workload", f"deployment/{args.deploy}")
    _print_kv("target", f"{args.target} ready pods")

<<<<<<< HEAD
    before = _run_replay(
        sim_env=sim_env,
        core=core,
        apps=apps,
        trace_path=trace_path,
=======
    step_paths = [trace_path]
    for action in PLANNED_ACTIONS:
        output_path = str(Path(".tmp") / f"demo-mvp-{action['type']}-{uuid.uuid4().hex[:8]}.msgpack")
        Path(".tmp").mkdir(parents=True, exist_ok=True)
        step_paths.append(_apply_action_to_trace(step_paths[-1], args.deploy, action, output_path))

    total_steps = len(step_paths) - 1
    snapshots: list[Snapshot] = []

    initial = _run_replay(
        sim_env=sim_env,
        core=core,
        apps=apps,
        trace_path=step_paths[0],
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        namespace=args.namespace,
        virtual_namespace=args.virtual_namespace,
        deploy=args.deploy,
        duration_s=args.duration,
<<<<<<< HEAD
        snapshot_timeout_s=args.poll_timeout,
        snapshot_predicate=before_predicate,
    )
    _format_snapshot("Before", before, args.target)

    print()
    print(
        "action          "
        f"reduce_cpu_small(step={cpu_change['step']}) "
        f"{cpu_change['from_cpu']} -> {cpu_change['to_cpu']}"
    )

    after = _run_replay(
        sim_env=sim_env,
        core=core,
        apps=apps,
        trace_path=fixed_trace_path,
        namespace=args.namespace,
        virtual_namespace=args.virtual_namespace,
        deploy=args.deploy,
        duration_s=args.duration,
        snapshot_timeout_s=args.poll_timeout,
        snapshot_predicate=after_predicate,
    )
    _format_snapshot("After", after, args.target)

    print()
    if _recovery_succeeded(before, after, args.target):
=======
        driver_timeout_s=args.driver_timeout,
        deploy_timeout_s=args.deploy_timeout,
        snapshot_timeout_s=args.poll_timeout,
        cleanup_timeout_s=args.cleanup_timeout,
        success_predicate=lambda snap: int(snap.obs.get("total", 0)) > 0 and int(snap.obs.get("unschedulable", 0)) > 0,
    )
    snapshots.append(initial)
    _format_step(0, total_steps, "failing trace", initial, args.target)

    for idx, action in enumerate(PLANNED_ACTIONS, start=1):
        print()
        print(
            "action          "
            f"{action['type']} ({action['summary']})"
        )
        if idx == total_steps:
            predicate = lambda snap, target=args.target: _final_success(snap, target)
        else:
            predicate = _all_expected_pods_ready
        snapshot = _run_replay(
            sim_env=sim_env,
            core=core,
            apps=apps,
            trace_path=step_paths[idx],
            namespace=args.namespace,
            virtual_namespace=args.virtual_namespace,
            deploy=args.deploy,
            duration_s=args.duration,
            driver_timeout_s=args.driver_timeout,
            deploy_timeout_s=args.deploy_timeout,
            snapshot_timeout_s=args.poll_timeout,
            cleanup_timeout_s=args.cleanup_timeout,
            success_predicate=predicate,
        )
        snapshots.append(snapshot)
        _format_step(idx, total_steps, action["focus"], snapshot, args.target)

    print()
    if _final_success(snapshots[-1], args.target):
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
        print("verdict         SUCCESS")
        return 0

    print("verdict         FAILURE")
    return 1


def build_parser() -> argparse.ArgumentParser:
<<<<<<< HEAD
    parser = argparse.ArgumentParser(description="Minimal terminal MVP demo")
=======
    parser = argparse.ArgumentParser(description="Step-by-step MVP terminal demo")
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    parser.add_argument("--trace", default=DEFAULT_TRACE, help="Input trace to replay")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="Source namespace for the Simulation object")
    parser.add_argument("--virtual-namespace", default=DEFAULT_VIRTUAL_NAMESPACE, help="Namespace where SimKube replays pods")
    parser.add_argument("--deploy", default=DEFAULT_DEPLOYMENT, help="Deployment name to observe")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_READY, help="Target ready pod count")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_S, help="Simulation duration in seconds")
<<<<<<< HEAD
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S, help="Max wait for each snapshot")
    parser.add_argument("--target-cpu", default=DEFAULT_TARGET_CPU, help="Post-remediation CPU request")
=======
    parser.add_argument("--driver-timeout", type=int, default=DEFAULT_DRIVER_TIMEOUT_S, help="Max wait for driver pod startup")
    parser.add_argument("--deploy-timeout", type=int, default=DEFAULT_DEPLOY_TIMEOUT_S, help="Max wait for deployment creation")
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S, help="Max wait for each step snapshot")
    parser.add_argument("--cleanup-timeout", type=int, default=DEFAULT_CLEANUP_TIMEOUT_S, help="Max wait for per-step cleanup in the replay namespace")
>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    try:
        return run_demo(args)
    except KeyboardInterrupt:
        print()
        print("verdict         INTERRUPTED")
        return 130
    except Exception as exc:
        print()
        print("verdict         FAILURE")
        print(f"error           {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
