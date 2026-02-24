#!/usr/bin/env python3
"""
ec2_one_step_from_lt.py

Usage (on your controller server):
  export AWS_REGION="us-east-1"
  export AWS_ACCESS_KEY_ID="..."
  export AWS_SECRET_ACCESS_KEY="..."
  export LAUNCH_TEMPLATE_ID="lt-0e714d89b56d21b82"
  export LAUNCH_TEMPLATE_VERSION="$Latest"   # optional
  export SSH_KEY_PATH="$HOME/.ssh/syncube-test-bob.pem"
  export SSH_USER="ubuntu"                # or ubuntu depending on AMI

  chmod 600 "$SSH_KEY_PATH"
  python ec2_one_step_from_lt.py
"""

import os
import socket
import subprocess
import textwrap
import time
from typing import Optional

import boto3


def wait_for_tcp(host: str, port: int, timeout_s: int = 600) -> None:
    """Wait until host:port accepts TCP connections."""
    deadline = time.time() + timeout_s
    last_err: Optional[Exception] = None
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=5):
                return
        except OSError as e:
            last_err = e
            time.sleep(2)
    raise TimeoutError(f"Timed out waiting for TCP {host}:{port}. Last error: {last_err}")


def ssh_run_script(host: str, user: str, key_path: str, script: str) -> str:
    """
    Run a bash script on the remote host via SSH and return combined stdout/stderr.
    """
    cmd = [
        "ssh",
        "-i", key_path,
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ConnectTimeout=10",
        f"{user}@{host}",
        "bash -s",
    ]
    p = subprocess.run(
        cmd,
        input=script,
        text=True,
        capture_output=True,
    )
    out = (p.stdout or "") + (p.stderr or "")
    if p.returncode != 0:
        raise RuntimeError(f"Remote script failed (exit {p.returncode}). Output:\n{out}")
    return out


def get_instance_public_ip(ec2, instance_id: str) -> str:
    """
    Describe instance and return PublicIpAddress. :contentReference[oaicite:1]{index=1}
    """
    r = ec2.describe_instances(InstanceIds=[instance_id])
    inst = r["Reservations"][0]["Instances"][0]
    ip = inst.get("PublicIpAddress")
    if not ip:
        # If this happens, your subnet/LT likely didn't assign a public IP.
        # You can still connect if the controller is in the same VPC and you use PrivateIpAddress.
        raise RuntimeError(
            f"Instance {instance_id} has no PublicIpAddress. "
            "Enable auto-assign public IP in the Launch Template/subnet, or run the controller inside the VPC."
        )
    return ip


def main() -> None:
    region = os.environ.get("AWS_REGION", "us-east-1")
    lt_id = os.environ["LAUNCH_TEMPLATE_ID"]
    lt_ver = os.environ.get("LAUNCH_TEMPLATE_VERSION", "$Latest")  # $Latest / $Default / number :contentReference[oaicite:2]{index=2}

    ssh_key = os.environ["SSH_KEY_PATH"]
    ssh_user = os.environ.get("SSH_USER", "ec2-user")

    ec2 = boto3.client("ec2", region_name=region)

    instance_id: Optional[str] = None
    try:
        # 1) Launch instance from Launch Template :contentReference[oaicite:3]{index=3}
        resp = ec2.run_instances(
            MinCount=1,
            MaxCount=1,
            LaunchTemplate={"LaunchTemplateId": lt_id, "Version": lt_ver},
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [{"Key": "Name", "Value": "sim-arena-one-step"}],
            }],
        )
        instance_id = resp["Instances"][0]["InstanceId"]
        print("Launched:", instance_id)

        # 2) Wait until instance is running :contentReference[oaicite:4]{index=4}
        ec2.get_waiter("instance_running").wait(InstanceIds=[instance_id])
        print("Running:", instance_id)

        # 3) Wait until system + instance status checks are OK :contentReference[oaicite:5]{index=5}
        ec2.get_waiter("instance_status_ok").wait(InstanceIds=[instance_id])
        print("Status OK:", instance_id)

        # 4) Get public IP and wait for SSH to come up
        ip = get_instance_public_ip(ec2, instance_id)
        print("Public IP:", ip)
        wait_for_tcp(ip, 22, timeout_s=600)
        print("SSH reachable:", ip)

        # 5) Remote script: clone sim-arena, venv, pip install -r, run one_step, cat runs/step.jsonl
        remote_script = textwrap.dedent(r"""
        set -euo pipefail

        # Ensure git exists (best-effort across common distros)
        if ! command -v git >/dev/null 2>&1; then
          if command -v apt-get >/dev/null 2>&1; then
            (command -v sudo >/dev/null 2>&1 && sudo apt-get update -y) || apt-get update -y
            (command -v sudo >/dev/null 2>&1 && sudo apt-get install -y git python3-venv) || apt-get install -y git python3-venv
          elif command -v yum >/dev/null 2>&1; then
            (command -v sudo >/dev/null 2>&1 && sudo yum install -y git python3) || yum install -y git python3
          fi
        fi

        # Use home dir
        cd ~
        if [ ! -d sim-arena ]; then
          git clone https://github.com/bobg0/sim-arena.git
        else
          cd sim-arena
          git pull || true
          cd ~
        fi

        cd sim-arena

        # Create venv if missing
        if [ ! -d .venv ]; then
          python3 -m venv .venv
        fi
        . .venv/bin/activate

        python -m pip install -U pip
        python -m pip install -r requirements.txt

        export PYTHONPATH="$(pwd)"
                                        
        cp demo/traces/trace-0001.msgpack /var/kind/cluster/trace-0001.msgpack 

        echo "=== Running one_step ==="
        python -m runner.one_step \
          --trace demo/traces/trace-0001.msgpack \
          --ns virtual-default \
          --deploy web \
          --target 3 \
          --duration 60 \

        echo "=== runs/step.jsonl ==="
        if [ -f runs/step.jsonl ]; then
          cat runs/step.jsonl
        else
          echo "runs/step.jsonl not found. Contents of runs/:"
          ls -la runs || true
        fi
        """)

        output = ssh_run_script(ip, ssh_user, ssh_key, remote_script)
        print("\n========== REMOTE OUTPUT BEGIN ==========\n")
        print(output.rstrip())
        print("\n========== REMOTE OUTPUT END ==========\n")

    finally:
        if instance_id:
            # 6) Terminate instance :contentReference[oaicite:6]{index=6}
            try:
                ec2.terminate_instances(InstanceIds=[instance_id])
                print("Terminated:", instance_id)
            except Exception as e:
                print(f"WARNING: failed to terminate {instance_id}: {e}")


if __name__ == "__main__":
    main()