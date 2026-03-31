"""
Minimal terminal demo for the presentation MVP.

Story:
1. Replay an existing failing trace.
2. Show pods stuck Pending because CPU requests are too high.
3. Apply one CPU remediation using the existing trace op semantics.
4. Replay the fixed trace and verify the pods become Ready.

Run from the repo root after activating the venv:
    python -m runner.demo_mvp
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

from env.actions.ops import reduce_cpu_small
from env.actions.trace_io import load_trace, save_trace
from env.sim_env import SimEnv
from observe.reader import current_requests, observe
from ops.hooks import run_hooks
from runner.safeguards import parse_cpu_to_millicores, validate_action


DEFAULT_TRACE = "demo/trace-cpu-slight.msgpack"
DEFAULT_NAMESPACE = "default"
DEFAULT_VIRTUAL_NAMESPACE = "virtual-default"
DEFAULT_DEPLOYMENT = "web"
DEFAULT_TARGET_READY = 3
DEFAULT_DURATION_S = 18
DEFAULT_TARGET_CPU = "16000m"
DEFAULT_POLL_TIMEOUT_S = 20
POLL_INTERVAL_S = 2


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
        if active_name.startswith("kind-"):
            cluster_name = active_name.removeprefix("kind-")
        else:
            cluster_name = "cluster"

    return Path.home() / ".local" / "kind-node-data" / cluster_name


def _extract_trace_state(trace_path: str, deploy: str) -> dict[str, Any]:
    trace = load_trace(trace_path)
    current_state = {"cpu": "0m", "memory": "0Mi", "replicas": 0}

    for event in trace.get("events", []):
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


def _list_pods(core: client.CoreV1Api, namespace: str, deploy: str) -> list[dict[str, str]]:
    pod_list = core.list_namespaced_pod(namespace=namespace, label_selector=f"app={deploy}")
    rows: list[dict[str, str]] = []

    for pod in sorted(pod_list.items, key=lambda item: item.metadata.name or ""):
        ready_count = 0
        total_count = 0
        reason = pod.status.reason or ""

        for status in pod.status.container_statuses or []:
            total_count += 1
            if status.ready:
                ready_count += 1
            if not reason and status.state and status.state.waiting:
                reason = status.state.waiting.reason or ""

        if not reason and pod.status.conditions:
            for condition in pod.status.conditions:
                if condition.type == "PodScheduled" and condition.status == "False":
                    reason = condition.reason or ""
                    break

        rows.append(
            {
                "name": pod.metadata.name or "<unknown>",
                "phase": pod.status.phase or "Unknown",
                "ready": f"{ready_count}/{total_count or 1}",
                "reason": reason or "-",
            }
        )

    return rows


def _snapshot(core: client.CoreV1Api, namespace: str, deploy: str) -> Snapshot:
    return Snapshot(
        obs=observe(namespace, deploy),
        resources=current_requests(namespace, deploy),
        pods=_list_pods(core, namespace, deploy),
    )


def _wait_for_driver(core: client.CoreV1Api, sim_name: str, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    label_selector = f"job-name=sk-{sim_name}-driver"

    while time.time() < deadline:
        pods = core.list_pod_for_all_namespaces(label_selector=label_selector).items
        if pods:
            phase = pods[0].status.phase or ""
            if phase in {"Running", "Succeeded"}:
                return
            if phase == "Failed":
                raise RuntimeError(f"driver pod failed for simulation {sim_name}")
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(f"driver pod did not become ready within {timeout_s}s")


def _wait_for_deployment(apps: client.AppsV1Api, namespace: str, deploy: str, timeout_s: int) -> None:
    deadline = time.time() + timeout_s

    while time.time() < deadline:
        try:
            apps.read_namespaced_deployment(name=deploy, namespace=namespace)
            return
        except ApiException as exc:
            if exc.status != 404:
                raise
        time.sleep(POLL_INTERVAL_S)

    raise TimeoutError(f"deployment/{deploy} did not appear in {namespace} within {timeout_s}s")


def _wait_for_snapshot(
    core: client.CoreV1Api,
    namespace: str,
    deploy: str,
    timeout_s: int,
    success_predicate,
) -> Snapshot:
    deadline = time.time() + timeout_s
    last = _snapshot(core, namespace, deploy)

    while time.time() < deadline:
        last = _snapshot(core, namespace, deploy)
        if success_predicate(last):
            return last
        time.sleep(POLL_INTERVAL_S)

    return last


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


def _run_replay(
    sim_env: SimEnv,
    core: client.CoreV1Api,
    apps: client.AppsV1Api,
    trace_path: str,
    namespace: str,
    virtual_namespace: str,
    deploy: str,
    duration_s: int,
    snapshot_timeout_s: int,
    snapshot_predicate,
) -> Snapshot:
    sim_name = f"demo-mvp-{uuid.uuid4().hex[:8]}"
    run_hooks("pre_start", virtual_namespace, deploy=deploy)
    cluster_trace = _prepare_trace_for_cluster(trace_path)
    handle = sim_env.create(
        name=sim_name,
        trace_path=cluster_trace,
        namespace=namespace,
        duration_s=duration_s,
    )

    try:
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


def run_demo(args: argparse.Namespace) -> int:
    trace_path = str(Path(args.trace))
    core, apps = _load_clients()
    sim_env = SimEnv()

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

    _print_banner("SimArena MVP Demo")
    _print_kv("trace", trace_path)
    _print_kv("namespace", args.virtual_namespace)
    _print_kv("workload", f"deployment/{args.deploy}")
    _print_kv("target", f"{args.target} ready pods")

    before = _run_replay(
        sim_env=sim_env,
        core=core,
        apps=apps,
        trace_path=trace_path,
        namespace=args.namespace,
        virtual_namespace=args.virtual_namespace,
        deploy=args.deploy,
        duration_s=args.duration,
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
        print("verdict         SUCCESS")
        return 0

    print("verdict         FAILURE")
    return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal terminal MVP demo")
    parser.add_argument("--trace", default=DEFAULT_TRACE, help="Input trace to replay")
    parser.add_argument("--namespace", default=DEFAULT_NAMESPACE, help="Source namespace for the Simulation object")
    parser.add_argument("--virtual-namespace", default=DEFAULT_VIRTUAL_NAMESPACE, help="Namespace where SimKube replays pods")
    parser.add_argument("--deploy", default=DEFAULT_DEPLOYMENT, help="Deployment name to observe")
    parser.add_argument("--target", type=int, default=DEFAULT_TARGET_READY, help="Target ready pod count")
    parser.add_argument("--duration", type=int, default=DEFAULT_DURATION_S, help="Simulation duration in seconds")
    parser.add_argument("--poll-timeout", type=int, default=DEFAULT_POLL_TIMEOUT_S, help="Max wait for each snapshot")
    parser.add_argument("--target-cpu", default=DEFAULT_TARGET_CPU, help="Post-remediation CPU request")
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
