# EC2 one_step Failure Reproduction - 2026-04-23

## Environment and execution context

The EC2 launch path was being validated using the correct key pair name and successful SSH access to the instance. SSH into the worker succeeded.

The command was run on the EC2 machine at:

```text
ubuntu@ip-172-31-13-64:~/work/sim-arena
```

This run used the intended credentials and trace path for the EC2 worker validation. The execution reproduced the zero-observation behavior already noted in prior documentation: the EC2 access path itself succeeded far enough to run `one_step`, but the `one_step` execution did not produce the expected deployment state.

## Command executed

```bash
python runner/one_step.py \
  --trace s3://diya-simarena-traces/demo/trace-mem-slight.msgpack \
  --ns default \
  --deploy web \
  --target 3 \
  --duration 40 \
  --agent greedy \
  --reward shaped \
  --log-level INFO
```

## Timeline of observed behavior

- S3 trace download started and completed successfully.
- AWS credentials were found in environment variables.
- `one_step` started with:
  - `sim_name=diag-266a28e6`
  - `ns=default`
  - `virtual namespace=virtual-default`
  - `trace=s3://diya-simarena-traces/demo/trace-mem-slight.msgpack`
  - `deploy=web`
  - `target=3`
  - `duration=40`
  - `agent=greedy`
  - `reward=shaped`
- The run waited for the driver pod with selector:
  `batch.kubernetes.io/job-name=sk-diag-266a28e6-driver`
- The driver pod did not enter Running state within the 150 second buffer.
- The run then waited for deployment `web` in namespace `virtual-default`.
- The deployment was not found within 90 seconds.
- The run later hit a Kubernetes 404 for deployments.apps `web` not found.
- The resulting observation was:
  `{'ready': 0, 'pending': 0, 'total': 0}`
- The current requests were:
  `{'cpu': '0', 'memory': '0', 'replicas': 0}`
- A safeguard blocked the action:
  `Memory would exceed limit: 35701915648 bytes > 34359738368 bytes (32Gi)`
- Step summary was:
  `action=bump_mem_small, reward=-0.54, changed=False`

## Failure characteristics

The workload/deployment `web` was absent from `virtual-default` during the observed window. Because the deployment was absent, observation returned zero pod counts and current requests returned zero CPU, memory, and replicas.

The run did not reach the expected deployment state for `web`. The agent selected `bump_mem_small`, but the safeguard blocked the action because it would exceed the 32Gi memory limit. The agent action did not change the environment state.

## Exact log excerpt

```text
2026-04-23 02:53:45,817 INFO Downloading s3://diya-simarena-traces/demo/trace-mem-slight.msgpack -> .tmp/trace-mem-slight.msgpack
2026-04-23 02:53:45,826 INFO Found credentials in environment variables.
2026-04-23 02:53:46,065 INFO S3 download complete.
2026-04-23 02:53:46,065 INFO Starting one_step run: sim_name=diag-266a28e6, ns=default (virtual=virtual-default), trace=s3://diya-simarena-traces/demo/trace-mem-slight.msgpack, deploy=web, target=3, duration=40, agent=greedy, reward=shaped
2026-04-23 02:53:46,129 INFO Waiting for driver pod (batch.kubernetes.io/job-name=sk-diag-266a28e6-driver) to start to eliminate cluster lag...
2026-04-23 02:56:18,016 WARNING Driver pod didn't enter Running state within 150s buffer. Proceeding anyway.
2026-04-23 02:56:18,017 INFO Waiting for deployment 'web' in virtual-default (driver applying trace)...
2026-04-23 02:57:48,372 WARNING Deployment 'web' not found within 90s. Proceeding anyway.
2026-04-23 02:57:48,373 INFO Waiting 5s (of 40s window, 242s elapsed since sim creation)...
Error reading deployment 'web': (404)
Reason: Not Found
HTTP response headers: HTTPHeaderDict({'Audit-Id': '6de22cd7-e382-4bf5-90ff-cecf3d736e4c', 'Cache-Control': 'no-cache, private', 'Content-Type': 'application/json', 'X-Kubernetes-Pf-Flowschema-Uid': '9e4f3885-d434-47ce-96d1-de89f92050a2', 'X-Kubernetes-Pf-Prioritylevel-Uid': '0c29fe15-4415-4ebe-bf4e-c1bae0e433de', 'Date': 'Thu, 23 Apr 2026 02:58:09 GMT', 'Content-Length': '208'})
HTTP response body: {"kind":"Status","apiVersion":"v1","metadata":{},"status":"Failure","message":"deployments.apps \"web\" not found","reason":"NotFound","details":{"name":"web","group":"apps","kind":"deployments"},"code":404}

2026-04-23 02:58:09,421 INFO Observation: {'ready': 0, 'pending': 0, 'total': 0}
2026-04-23 02:58:09,421 INFO Current requests: {'cpu': '0', 'memory': '0', 'replicas': 0}
2026-04-23 02:58:09,421 WARNING ⚠️  Action blocked by safeguards: Memory would exceed limit: 35701915648 bytes > 34359738368 bytes (32Gi)
2026-04-23 02:58:09,425 INFO Step Summary: action=bump_mem_small, reward=-0.54, changed=False
```

## Summary statement for future teams

On 2026-04-23, SSH access to the EC2 worker succeeded and `runner/one_step.py` was executed from `ubuntu@ip-172-31-13-64:~/work/sim-arena` using the intended S3 trace path. The trace download completed successfully and AWS credentials were available in the environment.

The run reproduced the zero-observation behavior documented previously. The driver pod did not enter Running within the configured buffer, deployment `web` was not observed in `virtual-default`, and Kubernetes returned a 404 for the deployment.

The resulting observation and current requests were zero-valued. The selected agent action was blocked by safeguards, and no environment state change was recorded.
