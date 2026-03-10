# Next Big Tasks — Task Breakdown for Parallel Work

Three people can each own one of the big tasks below. This doc breaks each into a detailed checklist so you know exactly what to do to complete your task.

**Context:** We want to scale from "one EC2 instance running sim-arena" to "many EC2 instances running simulations, coordinated by a central server that collects results and drives training."

---

## Task 1: Launching Multiple EC2 Instances

**Owner:** Person A  
**Goal:** Automate launching N EC2 instances from our AMI so we can run many simulations in parallel without manual clicks.

### Subtasks

- [ ] **1.1** Document or script: given a count N, launch N EC2 instances from AMI `ami-08d19a1b7f569b848` in `us-east-2` with:
  - Instance type (e.g. `c6a.xlarge`)
  - Same security group that allows SSH (and any ports needed for the communication protocol later)
  - Same key pair for team access
  - 100 GB gp3 storage
- [ ] **1.2** Decide how instance identity is tracked: tags (e.g. `Project=sim-arena`, `WorkerId=1`), naming convention (e.g. `sim-arena-worker-01`), or both.
- [ ] **1.3** Implement launch via one of:
  - AWS CLI script (e.g. `aws ec2 run-instances` in a loop or with `--count`)
  - Terraform / CloudFormation template
  - Python script using boto3
- [ ] **1.4** After launch, collect and store each instance’s **public IP** (and optionally private IP) in a form the central server or Person B’s protocol can use (e.g. a JSON file, env file, or simple key-value store).
- [ ] **1.5** Add a way to **terminate or stop** all N instances when a run is done (script or doc steps), so we don’t leave instances running.
- [ ] **1.6** (Optional) Auto-wait until instances pass status checks (2/2) and optionally run a simple SSH or health check before marking “ready.”
- [ ] **1.7** Document: where the script/template lives, how to run it, required env vars (e.g. `AWS_PROFILE` or keys), and how Person B gets the list of instance IPs/hostnames.

**Deliverable:** Script(s) or IaC plus a short doc (or section in this repo) so anyone can launch N workers and get a machine list for the communication layer.

---

## Task 2: Communication Protocol with Each EC2 Instance

**Owner:** Person B  
**Goal:** Define and implement how the central server (or operator) sends work to each EC2 instance and receives results back.

### Subtasks

- [ ] **2.1** Choose the protocol direction and style:
  - **Push:** Central server sends “run this job” to each instance (e.g. via SSH, agent on instance polling an API, or message queue).
  - **Pull:** Instances pull “next job” from a shared queue (e.g. SQS, Redis, or central API).
  - **Hybrid:** Central server pushes job config; instances pull trace/model from S3 and push results back to S3 or central API.
- [ ] **2.2** Define the **job payload** (what “work” means):
  - Trace path (e.g. `s3://bucket/demo/trace-mem-slight.msgpack`)
  - Namespace, deploy name, target replicas, agent, episodes/steps, duration, etc.
  - Any run ID or worker ID for tying results back.
- [ ] **2.3** Define the **result payload** (what comes back):
  - Run ID, worker ID, success/failure
  - Metrics (rewards, steps completed, etc.)
  - Where checkpoints/logs are written (e.g. S3 paths) if applicable.
- [ ] **2.4** Implement one of:
  - **SSH:** Central server runs `ssh -i key ubuntu@<IP> "cd ~/work/sim-arena && source .venv/bin/activate && python runner/train.py ..."` and parses stdout; capture logs to a file and optionally upload to S3.
  - **Queue (e.g. SQS):** Central server enqueues job messages; a small agent script on each EC2 instance polls, runs `train.py`/`one_step.py`, then enqueues result message or uploads result to S3 and notifies.
  - **REST/API:** Thin API on each instance (or a single coordinator API) that accepts “run job” and returns job ID; instances run async and post results to central server or S3.
- [ ] **2.5** Handle **timeouts and failures:** max wall time per job, what to do if an instance is unresponsive (mark failed, retry on another instance if applicable).
- [ ] **2.6** Ensure each instance has **credentials and env** needed to run (e.g. `simkube` K8s secret for S3, `AWS_*` or instance role). Document any one-time setup per instance after Person A launches them.
- [ ] **2.7** Document: protocol choice, message/API shape, how to run the “dispatcher” or “worker agent” from the central server and from the EC2 side.

**Deliverable:** A clear protocol (doc or OpenAPI/spec) plus code or scripts so the central server can assign work to the list of IPs from Task 1 and get results back.

---

## Task 3: Centralizing the Information Within the Server

**Owner:** Person C  
**Goal:** One place that holds “source of truth” for jobs, results, and (optionally) model state, and that can drive training across the workers.

### Subtasks

- [ ] **3.1** Define what “the server” is:
  - A machine (e.g. a laptop or a single EC2) that runs the orchestrator and stores data, or
  - A serverless/API (e.g. Lambda + API Gateway + DynamoDB or RDS), or
  - A container/service running in the cloud with a small DB or S3 as backend.
- [ ] **3.2** Design **job queue / job store:**
  - List of (job spec, status, assigned worker, result).
  - Could be: SQLite/Postgres table, JSON files in S3, DynamoDB, or in-memory + file backup for MVP.
- [ ] **3.3** Implement **job creation:** given a set of traces (or trace paths), agent config, and number of episodes/steps, create N jobs (e.g. one per trace or one per trace×episode) and put them in the queue.
- [ ] **3.4** Implement **result collection:** when Person B’s protocol reports “job X finished,” the server stores:
  - Success/failure, rewards, steps, run time
  - Pointers to logs/artifacts (e.g. S3 paths) if applicable.
- [ ] **3.5** **Aggregation and visibility:**
  - Aggregate metrics across jobs (e.g. mean reward per trace, success rate).
  - Simple dashboard or report (e.g. CSV, JSON summary, or a minimal web page) so the team can see progress and compare runs.
- [ ] **3.6** (Optional) **Model/checkpoint centralization:**
  - If training updates a policy: define where the “current” model lives (e.g. S3 bucket + version or path).
  - Workers pull latest model when starting a job; or a single “trainer” process on the server consumes results and updates the model, then distributes it.
- [ ] **3.7** **Integration points:**
  - Input: list of worker IPs (from Task 1) and job queue from Task 3.
  - Output: job assignments and result payloads that match what Person B’s protocol expects (Task 2).
- [ ] **3.8** Document: how to run the central server, env vars, where data is stored (paths, bucket, DB), and how to run a “full run” (create jobs → dispatch via Task 2 → collect results → view summary).

**Deliverable:** A runnable central service or script(s) that create jobs, receive results, store them in one place, and expose a minimal view of “all runs” for the team.

---

## Dependencies Between Tasks

| Task | Depends on | Others need from you |
|------|------------|----------------------|
| **1. Multiple EC2** | Nothing (can use existing AMI) | List of instance IPs (or a way to get them) after launch. |
| **2. Communication protocol** | List of instance IPs (from Task 1); job/result format (can align with Task 3 early) | Protocol spec and how to send one job and get one result. |
| **3. Central server** | Job/result format (align with Task 2) | Where jobs are stored and how the dispatcher gets the worker list (from Task 1). |

**Suggested order:**  
- **Week 1:** Agree on job and result payload (Tasks 2 and 3 owners). Person A delivers launch script + machine list.  
- **Week 2:** Person B delivers a minimal “send one job, get one result” flow. Person C delivers job store and result collection.  
- **Week 3:** Integrate: launch N instances (1), run dispatcher (2), create and collect jobs (3), then iterate.

---

## Quick Reference

| Task | Owner | Main deliverable |
|------|--------|-------------------|
| 1. Launching multiple EC2 instances | Person A | Script/IaC to launch N workers + list of IPs; doc for run/terminate. |
| 2. Communication protocol | Person B | Protocol (SSH/queue/API), job/result format, code to dispatch and receive. |
| 3. Centralizing information | Person C | Central job queue, result storage, aggregation, and minimal dashboard/report. |
