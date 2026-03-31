# SimArena Multi-Worker EC2 Runbook

This runbook completes Task 1 from [docs/NEXT_TASKS.md](/home/bogao/sim-arena/docs/NEXT_TASKS.md): launch `N` workers from the prebuilt SimArena AMI, tag them consistently, collect their IPs into a machine list, and shut them down cleanly when the run is over.

The automation lives in [ops/ec2_workers.py](/home/bogao/sim-arena/ops/ec2_workers.py).

The same module now exposes a library-style API for future in-process training integration:

```python
from ops.ec2_workers import LaunchConfig, CleanupConfig, launch_workers, cleanup_workers

launch = launch_workers(
    LaunchConfig(
        count=2,
        region="us-east-2",
        security_group_ids=["sg-..."], # sg-06cddec780dfbdae4 <-- find your on aws
        subnet_id="subnet-...", # subnet-09f1a971bd8077ea7 <-- find your own on aws
        bootstrap_secret=False,
    )
)

# launch.instances contains structured worker metadata.

cleanup_workers(
    CleanupConfig(
        action="terminate",
        region=launch.region,
        inventory_file=launch.inventory_path,
        require_confirmation=False,
    )
)
```

## What the script does

- Launches `N` EC2 instances from `ami-08d19a1b7f569b848` in `us-east-2`
- Uses a configurable instance type, defaulting to `c6a.xlarge`
- Uses `100 GB` `gp3` root storage
- Applies both a naming convention and tags:
  - `Name=sim-arena-worker-<run-id>-<worker-id>`
  - `Project=sim-arena`
  - `Role=worker`
  - `SimArenaRunId=<run-id>`
  - `WorkerId=<worker-id>`
- Waits for the instances to reach `running` and, by default, EC2 `2/2` status checks
- Optionally SSHes into each worker and creates or updates the `simkube` Kubernetes secret automatically
- Writes a JSON inventory file with instance IDs, public/private IPs, DNS names, tags, and bootstrap status
- Provides `list`, `stop`, and `terminate` commands for cleanup

## Human AWS setup before running the script

These are the values a human needs to confirm once in AWS. The script uses them, but it does not guess them blindly.

1. Confirm the region is `us-east-2`.
2. Confirm the AMI is `ami-08d19a1b7f569b848` (`simkube-simarena-s3-ready-2026-03-08`).
3. Confirm the EC2 key pair name is `bob-s3-test-key`.
4. Find the security group ID you want attached to every worker.
   Use the EC2 console on the launch page or on `EC2 > Security Groups`.
   The group must allow inbound SSH from your operator machine.
5. Pick a subnet that assigns public IPv4 addresses if you want the controller script to bootstrap workers over SSH.
   The safest approach is to pass `--subnet-id` explicitly instead of relying on the default subnet selection.
6. Confirm the S3 bucket name for traces is `bob-simarena-traces`.
   The current known-good trace path is `s3://bob-simarena-traces/demo/trace-mem-slight.msgpack`.

## Credentials

Use standard boto3 credential resolution on the machine where you run the script:

- `AWS_PROFILE=<profile>` if you use named credentials locally
- or `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, and optionally `AWS_SESSION_TOKEN`

The script reads the resolved credentials from boto3 and pushes them into the `simkube` Kubernetes secret on each worker during bootstrap. Nothing should be hardcoded into the script.

## Required local files

- The repo checked out locally
- The PEM file for the AWS key pair, currently `bob-s3-test-key.pem`

The default SSH key path expected by the script is:

```bash
/home/bogao/sim-arena/bob-s3-test-key.pem
```

If your PEM is elsewhere, pass `--ssh-key-path`.

## Launch command

Example:

```bash
cd /home/bogao/sim-arena
source .venv/bin/activate

python ops/ec2_workers.py launch \
  --count 3 \
  --region us-east-2 \
  --instance-type c6a.xlarge \
  --key-name bob-s3-test-key \
  --security-group-id sg-REPLACE_ME \
  --subnet-id subnet-REPLACE_ME
```

Notes:

- `--security-group-id` is required unless you instead use `--security-group-name`.
- `--subnet-id` is strongly recommended because it makes public IP behavior explicit.
- The script defaults to `100 GB gp3`, the SimArena AMI, SSH user `ubuntu`, and automatic `simkube` secret setup.
- If you want to skip secret bootstrap temporarily, add `--no-bootstrap-secret`.
- If you want a stable logical batch name, pass `--run-id`.

## What gets generated

The launch command writes a JSON inventory file under:

```bash
runs/ec2_workers/<run-id>.json
```

Example fields:

```json
{
  "run_id": "20260324-220000",
  "trace_bucket": "bob-simarena-traces",
  "trace_path": "s3://bob-simarena-traces/demo/trace-mem-slight.msgpack",
  "instances": [
    {
      "instance_id": "i-0123456789abcdef0",
      "name": "sim-arena-worker-20260324-220000-01",
      "public_ip": "18.123.45.67",
      "private_ip": "172.31.10.25",
      "bootstrap": {
        "secret_applied": true,
        "ssh_ready": true,
        "error": null
      }
    }
  ]
}
```

This file is the machine list Person B can consume for job dispatch.

## Smoke test

For the immediate AWS provisioning check, use the narrow smoke-test path:

```bash
python ops/ec2_workers.py smoke-test \
  --security-group-id sg-REPLACE_ME \
  --subnet-id subnet-REPLACE_ME
```

Behavior:

- launches `2` workers by default
- waits for `instance_running`
- captures instance IDs, IPs, states, and `run_id`
- writes the normal inventory file
- resolves the launched workers again from inventory
- terminates them automatically unless `--keep-instances` is passed

This intentionally does not require SSH bootstrap or remote workload execution, so it isolates the AWS multi-instance launch path.

## Listing workers later

From the inventory file:

```bash
python ops/ec2_workers.py list --inventory-file runs/ec2_workers/<run-id>.json
```

From AWS tags only:

```bash
python ops/ec2_workers.py list --run-id <run-id> --region us-east-2
```

## Cleanup

Terminate from the inventory file:

```bash
python ops/ec2_workers.py terminate --inventory-file runs/ec2_workers/<run-id>.json
```

Terminate by tag lookup:

```bash
python ops/ec2_workers.py terminate --run-id <run-id> --region us-east-2
```

Skip the confirmation prompt:

```bash
python ops/ec2_workers.py terminate --inventory-file runs/ec2_workers/<run-id>.json --yes
```

For debugging, you can stop instead of terminate:

```bash
python ops/ec2_workers.py stop --inventory-file runs/ec2_workers/<run-id>.json
```

Terminate remains the recommended default for ephemeral workers, because stopped instances still keep volumes and can continue costing money.

## Relationship to the single-instance AMI guide

[docs/EC2_SETUP_FROM_SCRATCH.md](/home/bogao/sim-arena/docs/EC2_SETUP_FROM_SCRATCH.md) remains the source for understanding what the AMI contains and how a single worker behaves after login.

This multi-worker runbook builds on that setup with:

- batch launch automation
- tagging and naming conventions
- automatic `simkube` secret setup
- machine inventory output for downstream orchestration
- bulk stop and terminate operations
