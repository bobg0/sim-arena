#!/usr/bin/env python3
"""Launch, inspect, and clean up batches of SimArena EC2 workers.

Future training-loop integration should call `launch_workers()` and
`cleanup_workers()` directly rather than shelling out. The API returns
structured dataclasses so a caller such as `runner/train.py` can keep worker
metadata in memory, optionally persist inventory, and later attach a separate
job-dispatch layer.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal

import boto3
from botocore.exceptions import ClientError


AMI_ID = "ami-08d19a1b7f569b848"
DEFAULT_REGION = "us-east-2"
DEFAULT_INSTANCE_TYPE = "c6a.xlarge"
DEFAULT_VOLUME_SIZE_GB = 100
DEFAULT_KEY_NAME = "bob-s3-test-key"
DEFAULT_SSH_USER = "ubuntu"
DEFAULT_WORKER_PREFIX = "sim-arena-worker"
DEFAULT_PROJECT_TAG = "sim-arena"
DEFAULT_TRACE_BUCKET = "bob-simarena-traces"
DEFAULT_TRACE_PATH = "s3://bob-simarena-traces/demo/trace-mem-slight.msgpack"

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INVENTORY_DIR = REPO_ROOT / "runs" / "ec2_workers"
DEFAULT_SSH_KEY_PATH = REPO_ROOT / "bob-s3-test-key.pem"

ProgressCallback = Callable[[str], None]
CleanupAction = Literal["stop", "terminate"]


@dataclass
class LaunchConfig:
    count: int
    region: str = DEFAULT_REGION
    ami_id: str = AMI_ID
    instance_type: str = DEFAULT_INSTANCE_TYPE
    key_name: str = DEFAULT_KEY_NAME
    security_group_ids: list[str] = field(default_factory=list)
    security_group_names: list[str] = field(default_factory=list)
    subnet_id: str | None = None
    volume_size: int = DEFAULT_VOLUME_SIZE_GB
    ssh_user: str = DEFAULT_SSH_USER
    ssh_key_path: str = str(DEFAULT_SSH_KEY_PATH)
    worker_prefix: str = DEFAULT_WORKER_PREFIX
    project_tag: str = DEFAULT_PROJECT_TAG
    run_id: str = field(default_factory=lambda: datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"))
    inventory_file: str | None = None
    trace_bucket: str = DEFAULT_TRACE_BUCKET
    trace_path: str = DEFAULT_TRACE_PATH
    wait_status_checks: bool = True
    wait_ssh: bool = True
    bootstrap_secret: bool = True
    startup_timeout: int = 900

    def inventory_path(self) -> Path:
        if self.inventory_file:
            return Path(self.inventory_file).expanduser().resolve()
        return (DEFAULT_INVENTORY_DIR / f"{self.run_id}.json").resolve()


@dataclass
class CleanupConfig:
    action: CleanupAction
    region: str = DEFAULT_REGION
    inventory_file: str | None = None
    run_id: str | None = None
    project_tag: str = DEFAULT_PROJECT_TAG
    require_confirmation: bool = True


@dataclass
class WorkerBootstrapState:
    secret_applied: bool = False
    ssh_ready: bool = False
    error: str | None = None


@dataclass
class WorkerRecord:
    instance_id: str
    name: str | None
    worker_id: str | None
    state: str
    public_ip: str | None
    private_ip: str | None
    public_dns: str | None
    private_dns: str | None
    launch_time: str | None
    tags: dict[str, str]
    bootstrap: WorkerBootstrapState = field(default_factory=WorkerBootstrapState)


@dataclass
class LaunchError:
    worker_name: str
    message: str


@dataclass
class LaunchResult:
    status: int
    run_id: str
    created_at: str
    region: str
    ami_id: str
    instance_type: str
    key_name: str
    security_group_ids: list[str]
    subnet_id: str | None
    volume_size_gb: int
    project_tag: str
    worker_prefix: str
    trace_bucket: str
    trace_path: str
    caller_identity: dict[str, str]
    inventory_path: str
    instances: list[WorkerRecord]
    launch_errors: list[LaunchError] = field(default_factory=list)

    def to_inventory_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "region": self.region,
            "ami_id": self.ami_id,
            "instance_type": self.instance_type,
            "key_name": self.key_name,
            "security_group_ids": self.security_group_ids,
            "subnet_id": self.subnet_id,
            "volume_size_gb": self.volume_size_gb,
            "project_tag": self.project_tag,
            "worker_prefix": self.worker_prefix,
            "trace_bucket": self.trace_bucket,
            "trace_path": self.trace_path,
            "instances": [worker_record_to_dict(worker) for worker in self.instances],
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "caller_identity": self.caller_identity,
            "inventory_path": self.inventory_path,
            "launch_errors": [asdict(item) for item in self.launch_errors],
            **self.to_inventory_dict(),
        }


@dataclass
class ResolvedWorkers:
    region: str
    source: str
    run_id: str | None
    project_tag: str | None
    inventory_path: str | None
    instances: list[WorkerRecord]

    @property
    def instance_ids(self) -> list[str]:
        return [worker.instance_id for worker in self.instances]

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "source": self.source,
            "run_id": self.run_id,
            "project_tag": self.project_tag,
            "inventory_path": self.inventory_path,
            "instances": [worker_record_to_dict(worker) for worker in self.instances],
        }


@dataclass
class CleanupResult:
    status: int
    action: CleanupAction
    resolved: ResolvedWorkers

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "action": self.action,
            "resolved": self.resolved.to_dict(),
        }


@dataclass
class SmokeTestResult:
    status: int
    launch: LaunchResult
    observed: ResolvedWorkers
    cleanup: CleanupResult | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "launch": self.launch.to_dict(),
            "observed": self.observed.to_dict(),
            "cleanup": None if self.cleanup is None else self.cleanup.to_dict(),
        }


@dataclass
class PendingLaunch:
    worker_id: str
    instance_id: str
    name: str


def add_launch_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--count", type=int, help="Number of workers to launch.")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION))
    parser.add_argument("--ami-id", default=AMI_ID)
    parser.add_argument("--instance-type", default=DEFAULT_INSTANCE_TYPE)
    parser.add_argument("--key-name", default=os.environ.get("SIM_ARENA_KEY_NAME", DEFAULT_KEY_NAME))
    parser.add_argument(
        "--security-group-id",
        action="append",
        dest="security_group_ids",
        default=[],
        help="Security group ID to attach. Repeat for multiple groups.",
    )
    parser.add_argument(
        "--security-group-name",
        action="append",
        dest="security_group_names",
        default=[],
        help="Security group name to resolve in the target region. Repeat for multiple groups.",
    )
    parser.add_argument("--subnet-id", help="Subnet to launch into. Recommended for stable networking.")
    parser.add_argument("--volume-size", type=int, default=DEFAULT_VOLUME_SIZE_GB)
    parser.add_argument("--ssh-user", default=DEFAULT_SSH_USER)
    parser.add_argument(
        "--ssh-key-path",
        default=os.environ.get("SIM_ARENA_SSH_KEY_PATH", str(DEFAULT_SSH_KEY_PATH)),
        help="Local PEM path used for bootstrap SSH.",
    )
    parser.add_argument("--worker-prefix", default=DEFAULT_WORKER_PREFIX)
    parser.add_argument("--project-tag", default=DEFAULT_PROJECT_TAG)
    parser.add_argument(
        "--run-id",
        default=datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S"),
        help="Logical batch ID used in tags and inventory filename.",
    )
    parser.add_argument(
        "--inventory-file",
        help="Where to write inventory JSON. Defaults to runs/ec2_workers/<run-id>.json.",
    )
    parser.add_argument("--trace-bucket", default=DEFAULT_TRACE_BUCKET)
    parser.add_argument("--trace-path", default=DEFAULT_TRACE_PATH)
    parser.add_argument(
        "--wait-status-checks",
        action="store_true",
        default=True,
        help="Wait for EC2 status checks to reach 2/2 before bootstrapping.",
    )
    parser.add_argument(
        "--no-wait-status-checks",
        action="store_false",
        dest="wait_status_checks",
        help="Do not wait for 2/2 EC2 status checks.",
    )
    parser.add_argument(
        "--wait-ssh",
        action="store_true",
        default=True,
        help="Wait for TCP/22 before bootstrap.",
    )
    parser.add_argument(
        "--no-wait-ssh",
        action="store_false",
        dest="wait_ssh",
        help="Skip TCP/22 checks.",
    )
    parser.add_argument(
        "--bootstrap-secret",
        action="store_true",
        default=True,
        help="SSH into each worker and create/update the simkube secret.",
    )
    parser.add_argument(
        "--no-bootstrap-secret",
        action="store_false",
        dest="bootstrap_secret",
        help="Skip the post-launch Kubernetes secret setup.",
    )
    parser.add_argument(
        "--startup-timeout",
        type=int,
        default=900,
        help="Maximum seconds to wait for SSH or bootstrap steps.",
    )


def add_cleanup_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--inventory-file", help="Inventory JSON created by the launch command.")
    parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION))
    parser.add_argument("--run-id", help="Batch ID used in SimArenaRunId tags.")
    parser.add_argument("--project-tag", default=DEFAULT_PROJECT_TAG)
    parser.add_argument("--yes", action="store_true", help="Skip the safety confirmation prompt.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Manage batches of SimArena EC2 workers from the prebuilt AMI."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    launch_parser = subparsers.add_parser("launch", help="Launch N worker instances.")
    add_launch_args(launch_parser)

    smoke_parser = subparsers.add_parser(
        "smoke-test",
        help="Launch a small batch, record metadata, and terminate it to prove AWS provisioning works.",
    )
    add_launch_args(smoke_parser)
    smoke_parser.set_defaults(
        count=2,
        bootstrap_secret=False,
        wait_ssh=False,
        wait_status_checks=False,
    )
    smoke_parser.add_argument(
        "--keep-instances",
        action="store_true",
        help="Skip automatic termination for debugging.",
    )

    list_parser = subparsers.add_parser("list", help="Show workers from inventory or a tagged run.")
    list_parser.add_argument("--inventory-file", help="Existing inventory JSON to print.")
    list_parser.add_argument("--region", default=os.environ.get("AWS_DEFAULT_REGION", DEFAULT_REGION))
    list_parser.add_argument("--run-id", help="Resolve running instances by SimArenaRunId tag.")
    list_parser.add_argument("--project-tag", default=DEFAULT_PROJECT_TAG)

    terminate_parser = subparsers.add_parser("terminate", help="Terminate workers from inventory or a tagged run.")
    add_cleanup_args(terminate_parser)

    stop_parser = subparsers.add_parser("stop", help="Stop workers from inventory or a tagged run.")
    add_cleanup_args(stop_parser)

    return parser.parse_args()


def worker_record_to_dict(worker: WorkerRecord) -> dict[str, Any]:
    payload = asdict(worker)
    payload["bootstrap"] = asdict(worker.bootstrap)
    return payload


def build_session(region: str) -> boto3.session.Session:
    return boto3.session.Session(region_name=region)


def normalize_launch_config(args: argparse.Namespace) -> LaunchConfig:
    if args.count is None:
        raise SystemExit("--count is required.")
    return LaunchConfig(
        count=args.count,
        region=args.region,
        ami_id=args.ami_id,
        instance_type=args.instance_type,
        key_name=args.key_name,
        security_group_ids=list(args.security_group_ids),
        security_group_names=list(args.security_group_names),
        subnet_id=args.subnet_id,
        volume_size=args.volume_size,
        ssh_user=args.ssh_user,
        ssh_key_path=args.ssh_key_path,
        worker_prefix=args.worker_prefix,
        project_tag=args.project_tag,
        run_id=args.run_id,
        inventory_file=args.inventory_file,
        trace_bucket=args.trace_bucket,
        trace_path=args.trace_path,
        wait_status_checks=args.wait_status_checks,
        wait_ssh=args.wait_ssh,
        bootstrap_secret=args.bootstrap_secret,
        startup_timeout=args.startup_timeout,
    )


def normalize_cleanup_config(args: argparse.Namespace, action: CleanupAction) -> CleanupConfig:
    return CleanupConfig(
        action=action,
        region=args.region,
        inventory_file=args.inventory_file,
        run_id=args.run_id,
        project_tag=args.project_tag,
        require_confirmation=not args.yes,
    )


def ensure_parent_dir(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def write_inventory(path: Path, payload: dict[str, Any]) -> None:
    ensure_parent_dir(path)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def read_inventory(path_str: str) -> dict[str, Any]:
    return json.loads(Path(path_str).expanduser().resolve().read_text(encoding="utf-8"))


def verify_credentials(session: boto3.session.Session) -> dict[str, str]:
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    return {
        "account": identity["Account"],
        "arn": identity["Arn"],
        "user_id": identity["UserId"],
    }


def validate_launch_config(config: LaunchConfig) -> None:
    if config.count <= 0:
        raise SystemExit("--count must be at least 1.")
    if not config.security_group_ids and not config.security_group_names:
        raise SystemExit("Provide at least one --security-group-id or --security-group-name.")
    if config.bootstrap_secret:
        ssh_key_path = Path(config.ssh_key_path).expanduser().resolve()
        if not ssh_key_path.exists():
            raise SystemExit(f"SSH key not found: {ssh_key_path}")


def resolve_security_group_ids(ec2: Any, ids: list[str], names: list[str]) -> list[str]:
    resolved = list(ids)
    if not names:
        return resolved
    response = ec2.describe_security_groups(Filters=[{"Name": "group-name", "Values": names}])
    found = {group["GroupName"]: group["GroupId"] for group in response["SecurityGroups"]}
    missing = [name for name in names if name not in found]
    if missing:
        raise SystemExit(f"Could not resolve security groups by name: {', '.join(missing)}")
    resolved.extend(found[name] for name in names)
    return resolved


def build_worker_tags(config: LaunchConfig, worker_id: str, name: str) -> list[dict[str, str]]:
    return [
        {"Key": "Name", "Value": name},
        {"Key": "Project", "Value": config.project_tag},
        {"Key": "Role", "Value": "worker"},
        {"Key": "SimArenaRunId", "Value": config.run_id},
        {"Key": "WorkerId", "Value": worker_id},
        {"Key": "TraceBucket", "Value": config.trace_bucket},
        {"Key": "TracePath", "Value": config.trace_path},
    ]


def build_run_instances_request(
    config: LaunchConfig,
    *,
    security_group_ids: list[str],
    worker_id: str,
    name: str,
) -> dict[str, Any]:
    tags = build_worker_tags(config, worker_id=worker_id, name=name)
    request: dict[str, Any] = {
        "ImageId": config.ami_id,
        "InstanceType": config.instance_type,
        "KeyName": config.key_name,
        "MinCount": 1,
        "MaxCount": 1,
        "TagSpecifications": [
            {"ResourceType": "instance", "Tags": tags},
            {"ResourceType": "volume", "Tags": tags},
        ],
        "BlockDeviceMappings": [
            {
                "DeviceName": "/dev/sda1",
                "Ebs": {
                    "VolumeSize": config.volume_size,
                    "VolumeType": "gp3",
                    "DeleteOnTermination": True,
                },
            }
        ],
    }
    if config.subnet_id:
        request["NetworkInterfaces"] = [
            {
                "DeviceIndex": 0,
                "SubnetId": config.subnet_id,
                "Groups": security_group_ids,
                "AssociatePublicIpAddress": True,
                "DeleteOnTermination": True,
            }
        ]
    else:
        request["SecurityGroupIds"] = security_group_ids
    return request


def launch_worker_instances(
    ec2: Any,
    config: LaunchConfig,
    *,
    security_group_ids: list[str],
    progress: ProgressCallback | None = None,
) -> tuple[list[PendingLaunch], list[LaunchError]]:
    launched: list[PendingLaunch] = []
    errors: list[LaunchError] = []
    for index in range(1, config.count + 1):
        worker_id = f"{index:02d}"
        name = f"{config.worker_prefix}-{config.run_id}-{worker_id}"
        request = build_run_instances_request(
            config,
            security_group_ids=security_group_ids,
            worker_id=worker_id,
            name=name,
        )
        try:
            response = ec2.run_instances(**request)
            instance_id = response["Instances"][0]["InstanceId"]
            launched.append(PendingLaunch(worker_id=worker_id, instance_id=instance_id, name=name))
            if progress:
                progress(f"Launched {name}: {instance_id}")
        except ClientError as exc:
            errors.append(LaunchError(worker_name=name, message=str(exc)))
            if progress:
                progress(f"Launch failed for {name}: {exc}")
    return launched, errors


def wait_for_instances_readiness(
    ec2: Any,
    instance_ids: list[str],
    *,
    wait_status_checks: bool,
    progress: ProgressCallback | None = None,
) -> None:
    ec2.get_waiter("instance_running").wait(InstanceIds=instance_ids)
    if progress:
        progress("Instances are running.")
    if wait_status_checks:
        ec2.get_waiter("instance_status_ok").wait(InstanceIds=instance_ids)
        if progress:
            progress("Instances passed EC2 status checks (2/2).")


def describe_instances(ec2: Any, instance_ids: list[str]) -> dict[str, dict[str, Any]]:
    described: dict[str, dict[str, Any]] = {}
    if not instance_ids:
        return described
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(InstanceIds=instance_ids):
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                described[instance["InstanceId"]] = instance
    return described


def extract_tags(instance: dict[str, Any]) -> dict[str, str]:
    return {tag["Key"]: tag["Value"] for tag in instance.get("Tags", [])}


def instance_to_worker_record(instance: dict[str, Any]) -> WorkerRecord:
    tags = extract_tags(instance)
    return WorkerRecord(
        instance_id=instance["InstanceId"],
        name=tags.get("Name"),
        worker_id=tags.get("WorkerId"),
        state=instance["State"]["Name"],
        public_ip=instance.get("PublicIpAddress"),
        private_ip=instance.get("PrivateIpAddress"),
        public_dns=instance.get("PublicDnsName"),
        private_dns=instance.get("PrivateDnsName"),
        launch_time=instance.get("LaunchTime").isoformat() if instance.get("LaunchTime") else None,
        tags=tags,
    )


def get_secret_material(session: boto3.session.Session, region: str) -> dict[str, str]:
    credentials = session.get_credentials()
    if credentials is None:
        raise SystemExit("No AWS credentials found in the current boto3 session.")
    frozen = credentials.get_frozen_credentials()
    material = {
        "AWS_ACCESS_KEY_ID": frozen.access_key,
        "AWS_SECRET_ACCESS_KEY": frozen.secret_key,
        "AWS_DEFAULT_REGION": region,
    }
    if frozen.token:
        material["AWS_SESSION_TOKEN"] = frozen.token
    return material


def wait_for_tcp(host: str, port: int, timeout_s: int) -> None:
    deadline = time.time() + timeout_s
    last_error: OSError | None = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError as exc:
            last_error = exc
            time.sleep(5)
    raise TimeoutError(f"Timed out waiting for {host}:{port}. Last error: {last_error}")


def ssh_run_script(host: str, user: str, key_path: str, script: str, timeout_s: int) -> str:
    command = [
        "ssh",
        "-i",
        key_path,
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "UserKnownHostsFile=/dev/null",
        "-o",
        "ConnectTimeout=15",
        f"{user}@{host}",
        "bash -s",
    ]
    completed = subprocess.run(
        command,
        input=script,
        text=True,
        capture_output=True,
        timeout=timeout_s,
    )
    output = (completed.stdout or "") + (completed.stderr or "")
    if completed.returncode != 0:
        raise RuntimeError(output.strip() or f"SSH command failed with exit code {completed.returncode}")
    return output


def bootstrap_simkube_secret(
    host: str,
    user: str,
    key_path: str,
    secret_material: dict[str, str],
    timeout_s: int,
) -> str:
    env_lines = "\n".join(
        f"export {name}={shlex.quote(value)}"
        for name, value in secret_material.items()
    )
    session_token_line = ""
    if "AWS_SESSION_TOKEN" in secret_material:
        session_token_line = '  --from-literal=AWS_SESSION_TOKEN="$AWS_SESSION_TOKEN" \\\n'

    remote_script = f"""set -euo pipefail
{env_lines}

source ~/.bashrc >/dev/null 2>&1 || true
unset KUBECONFIG
kubectl get nodes >/dev/null
kubectl create secret generic simkube -n simkube \\
  --from-literal=AWS_ACCESS_KEY_ID="$AWS_ACCESS_KEY_ID" \\
  --from-literal=AWS_SECRET_ACCESS_KEY="$AWS_SECRET_ACCESS_KEY" \\
  --from-literal=AWS_DEFAULT_REGION="$AWS_DEFAULT_REGION" \\
{session_token_line}\
  --dry-run=client -o yaml | kubectl apply -f -
kubectl get secret simkube -n simkube >/dev/null
"""
    return ssh_run_script(
        host=host,
        user=user,
        key_path=key_path,
        script=remote_script,
        timeout_s=timeout_s,
    )


def bootstrap_worker_instances(
    session: boto3.session.Session,
    config: LaunchConfig,
    workers: list[WorkerRecord],
    *,
    progress: ProgressCallback | None = None,
) -> None:
    if not config.bootstrap_secret:
        return

    secret_material = get_secret_material(session, config.region)
    ssh_key_path = str(Path(config.ssh_key_path).expanduser().resolve())
    for worker in workers:
        if not worker.public_ip:
            worker.bootstrap.error = "No public IP available for SSH bootstrap."
            continue
        if config.wait_ssh:
            wait_for_tcp(worker.public_ip, 22, timeout_s=config.startup_timeout)
        worker.bootstrap.ssh_ready = True
        if progress:
            progress(f"SSH reachable for {worker.name} at {worker.public_ip}")
        try:
            bootstrap_simkube_secret(
                host=worker.public_ip,
                user=config.ssh_user,
                key_path=ssh_key_path,
                secret_material=secret_material,
                timeout_s=config.startup_timeout,
            )
            worker.bootstrap.secret_applied = True
            if progress:
                progress(f"simkube secret applied on {worker.name}")
        except Exception as exc:  # noqa: BLE001
            worker.bootstrap.error = str(exc)
            if progress:
                progress(f"Bootstrap failed on {worker.name}: {exc}")


def assemble_launch_result(
    *,
    config: LaunchConfig,
    caller_identity: dict[str, str],
    security_group_ids: list[str],
    workers: list[WorkerRecord],
    launch_errors: list[LaunchError],
) -> LaunchResult:
    return LaunchResult(
        status=0 if workers else 1,
        run_id=config.run_id,
        created_at=datetime.now(timezone.utc).isoformat(),
        region=config.region,
        ami_id=config.ami_id,
        instance_type=config.instance_type,
        key_name=config.key_name,
        security_group_ids=security_group_ids,
        subnet_id=config.subnet_id,
        volume_size_gb=config.volume_size,
        project_tag=config.project_tag,
        worker_prefix=config.worker_prefix,
        trace_bucket=config.trace_bucket,
        trace_path=config.trace_path,
        caller_identity=caller_identity,
        inventory_path=str(config.inventory_path()),
        instances=workers,
        launch_errors=launch_errors,
    )


def launch_workers(config: LaunchConfig, *, progress: ProgressCallback | None = None) -> LaunchResult:
    validate_launch_config(config)
    session = build_session(config.region)
    caller_identity = verify_credentials(session)
    ec2 = session.client("ec2")
    security_group_ids = resolve_security_group_ids(ec2, config.security_group_ids, config.security_group_names)

    launched, launch_errors = launch_worker_instances(
        ec2,
        config,
        security_group_ids=security_group_ids,
        progress=progress,
    )
    if not launched:
        raise SystemExit("No instances were launched successfully.")

    instance_ids = [item.instance_id for item in launched]
    wait_for_instances_readiness(
        ec2,
        instance_ids,
        wait_status_checks=config.wait_status_checks,
        progress=progress,
    )

    described = describe_instances(ec2, instance_ids)
    workers = [instance_to_worker_record(described[item.instance_id]) for item in launched]
    bootstrap_worker_instances(session, config, workers, progress=progress)

    result = assemble_launch_result(
        config=config,
        caller_identity=caller_identity,
        security_group_ids=security_group_ids,
        workers=workers,
        launch_errors=launch_errors,
    )
    write_inventory(config.inventory_path(), result.to_inventory_dict())
    return result


def inventory_payload_to_resolved(payload: dict[str, Any], *, region: str, inventory_path: str) -> ResolvedWorkers:
    workers: list[WorkerRecord] = []
    for item in payload.get("instances", []):
        bootstrap_payload = item.get("bootstrap", {})
        workers.append(
            WorkerRecord(
                instance_id=item["instance_id"],
                name=item.get("name"),
                worker_id=item.get("worker_id"),
                state=item.get("state", "unknown"),
                public_ip=item.get("public_ip"),
                private_ip=item.get("private_ip"),
                public_dns=item.get("public_dns"),
                private_dns=item.get("private_dns"),
                launch_time=item.get("launch_time"),
                tags=item.get("tags", {}),
                bootstrap=WorkerBootstrapState(
                    secret_applied=bootstrap_payload.get("secret_applied", False),
                    ssh_ready=bootstrap_payload.get("ssh_ready", False),
                    error=bootstrap_payload.get("error"),
                ),
            )
        )
    return ResolvedWorkers(
        region=region,
        source="inventory",
        run_id=payload.get("run_id"),
        project_tag=payload.get("project_tag"),
        inventory_path=inventory_path,
        instances=workers,
    )


def collect_instances_for_run(ec2: Any, project_tag: str, run_id: str) -> list[dict[str, Any]]:
    filters = [
        {"Name": "tag:Project", "Values": [project_tag]},
        {"Name": "tag:SimArenaRunId", "Values": [run_id]},
        {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
    ]
    paginator = ec2.get_paginator("describe_instances")
    instances: list[dict[str, Any]] = []
    for page in paginator.paginate(Filters=filters):
        for reservation in page["Reservations"]:
            instances.extend(reservation["Instances"])
    return instances


def resolve_workers(
    *,
    region: str,
    inventory_file: str | None = None,
    run_id: str | None = None,
    project_tag: str = DEFAULT_PROJECT_TAG,
    session: boto3.session.Session | None = None,
) -> ResolvedWorkers:
    if inventory_file:
        inventory_path = str(Path(inventory_file).expanduser().resolve())
        return inventory_payload_to_resolved(
            read_inventory(inventory_path),
            region=region,
            inventory_path=inventory_path,
        )
    if run_id:
        active_session = session or build_session(region)
        ec2 = active_session.client("ec2")
        instances = collect_instances_for_run(ec2, project_tag, run_id)
        return ResolvedWorkers(
            region=region,
            source="tags",
            run_id=run_id,
            project_tag=project_tag,
            inventory_path=None,
            instances=[instance_to_worker_record(instance) for instance in instances],
        )
    raise SystemExit("Provide --inventory-file or --run-id.")


def prompt_for_confirmation(command_name: str, instance_ids: list[str]) -> None:
    response = input(f"{command_name} {len(instance_ids)} instance(s) ({', '.join(instance_ids)})? [y/N] ").strip()
    if response.lower() not in {"y", "yes"}:
        raise SystemExit("Cancelled.")


def cleanup_workers(
    config: CleanupConfig,
    *,
    progress: ProgressCallback | None = None,
) -> CleanupResult:
    session = build_session(config.region)
    ec2 = session.client("ec2")
    resolved = resolve_workers(
        region=config.region,
        inventory_file=config.inventory_file,
        run_id=config.run_id,
        project_tag=config.project_tag,
        session=session,
    )

    if not resolved.instance_ids:
        return CleanupResult(status=0, action=config.action, resolved=resolved)

    if config.require_confirmation:
        prompt_for_confirmation(config.action, resolved.instance_ids)

    if config.action == "terminate":
        ec2.terminate_instances(InstanceIds=resolved.instance_ids)
    elif config.action == "stop":
        ec2.stop_instances(InstanceIds=resolved.instance_ids)
    else:
        raise SystemExit(f"Unsupported action: {config.action}")

    if progress:
        progress(f"{config.action.title()} requested for {len(resolved.instance_ids)} instance(s).")
    return CleanupResult(status=0, action=config.action, resolved=resolved)


def run_smoke_test(config: LaunchConfig, keep_instances: bool = False) -> SmokeTestResult:
    launch_result = launch_workers(config)
    observed = resolve_workers(region=config.region, inventory_file=launch_result.inventory_path)
    cleanup_result: CleanupResult | None = None
    if not keep_instances:
        cleanup_result = cleanup_workers(
            CleanupConfig(
                action="terminate",
                region=config.region,
                inventory_file=launch_result.inventory_path,
                require_confirmation=False,
            )
        )
    return SmokeTestResult(
        status=0,
        launch=launch_result,
        observed=observed,
        cleanup=cleanup_result,
    )


def print_launch_summary(result: LaunchResult) -> None:
    print(f"AWS caller: {result.caller_identity['arn']} (account {result.caller_identity['account']})")
    print(f"Run ID: {result.run_id}")
    for worker in result.instances:
        print(f"{worker.name}: {worker.instance_id} state={worker.state} public_ip={worker.public_ip}")
        if worker.bootstrap.secret_applied:
            print("  bootstrap: simkube secret applied")
        elif worker.bootstrap.error:
            print(f"  bootstrap: {worker.bootstrap.error}")
    for item in result.launch_errors:
        print(f"Launch error for {item.worker_name}: {item.message}", file=sys.stderr)
    print(f"Inventory written to {result.inventory_path}")


def print_resolved_workers(resolved: ResolvedWorkers) -> None:
    print(json.dumps(resolved.to_dict(), indent=2, sort_keys=True))


def print_cleanup_summary(result: CleanupResult) -> None:
    if not result.resolved.instance_ids:
        print("No matching instances found.")
        return
    print(f"{result.action.title()} requested for {len(result.resolved.instance_ids)} instance(s).")


def print_smoke_test_summary(result: SmokeTestResult) -> None:
    summary = {
        "status": result.status,
        "run_id": result.launch.run_id,
        "inventory_path": result.launch.inventory_path,
        "instances": [
            {
                "instance_id": worker.instance_id,
                "name": worker.name,
                "state": worker.state,
                "public_ip": worker.public_ip,
                "private_ip": worker.private_ip,
            }
            for worker in result.observed.instances
        ],
        "cleanup_action": None if result.cleanup is None else result.cleanup.action,
    }
    print(json.dumps(summary, indent=2, sort_keys=True))


def main() -> int:
    args = parse_args()
    if args.command == "launch":
        result = launch_workers(normalize_launch_config(args), progress=print)
        print_launch_summary(result)
        return 0 if result.status == 0 else 1
    if args.command == "smoke-test":
        result = run_smoke_test(
            normalize_launch_config(args),
            keep_instances=args.keep_instances,
        )
        print_smoke_test_summary(result)
        return 0 if result.status == 0 else 1
    if args.command == "list":
        print_resolved_workers(
            resolve_workers(
                region=args.region,
                inventory_file=args.inventory_file,
                run_id=args.run_id,
                project_tag=args.project_tag,
            )
        )
        return 0
    if args.command == "terminate":
        result = cleanup_workers(normalize_cleanup_config(args, "terminate"), progress=print)
        print_cleanup_summary(result)
        return 0 if result.status == 0 else 1
    if args.command == "stop":
        result = cleanup_workers(normalize_cleanup_config(args, "stop"), progress=print)
        print_cleanup_summary(result)
        return 0 if result.status == 0 else 1
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
