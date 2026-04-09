# Training Server (Design Spec — Not Yet Implemented)

> **Note:** This document describes a planned Flask-based training server dashboard. The file `training_server.py` does **not currently exist** in this repo. The actual coordination between workers is handled by `protocol/sync_server.py` (S3-based FedAvg) and `protocol/dispatch.py` (job submission CLI). See `docs/WORKER_PROTOCOL.md` for the working implementation.

---

The training server provides a centralized web interface for managing distributed DQN training runs across multiple EC2 instances.

## Features

- **Web Dashboard**: Monitor training runs with real-time progress updates
- **Run Management**: Create, start, stop, and track training runs
- **Persistent Storage**: SQLite database for run metadata and status
- **REST API**: Programmatic access to training operations
- **Background Processing**: Training runs execute in background threads
- **Task Integration**: Uses Task 1 (EC2 launching) and Task 2 (job protocol) implementations

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│   Web Browser   │────│  Training Server │────│     SQLite DB   │
│   Dashboard     │    │    (Flask)       │    │   (runs.db)     │
└─────────────────┘    └──────────────────┘    └─────────────────┘
                              │
                              │ Uses Task 1 + Task 2
                              ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │ Task 1: EC2     │    │ Task 2: Job     │
                       │ launch_workers()│    │ Protocol       │
                       └─────────────────┘    └─────────────────┘
                              │                       │
                              ▼                       ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   EC2 Workers   │────│       S3        │
                       │                 │    │   (jobs/results)│
                       └─────────────────┘    └─────────────────┘
```

## Task Integration

This training server directly integrates with the existing Task 1 and Task 2 implementations:

### Task 1 Integration (EC2 Launching)
- Uses `ops/ec2_workers.launch_workers()` to start EC2 instances
- Uses `ops/ec2_workers.cleanup_workers()` to terminate instances
- No launch templates required - instances are launched directly

### Task 2 Integration (Communication Protocol)
- Extended `protocol/schemas.py` with `job_type` field for experience collection jobs
- Added `transitions_s3_uri` to JobResult for experience collection output location
- Uses `protocol/dispatch.submit_experience_collection_job()` to dispatch jobs
- Workers process jobs via `protocol/worker.py` with new experience collection support

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Start the server:
   ```bash
   python training_server.py --s3-bucket your-bucket-name
   ```

3. Open http://localhost:5000 in your browser

4. Create a new training run using the web form

## API Endpoints

### GET /runs
List all training runs.

**Response:**
```json
[
  {
    "run_id": "run_1640995200",
    "status": "running",
    "s3_bucket": "my-bucket",
    "num_workers": 5,
    "current_iteration": 3,
    "max_iterations": 10,
    "total_transitions": 1500,
    "created_at": "2023-12-31T12:00:00Z",
    "started_at": "2023-12-31T12:01:00Z"
  }
]
```

### POST /runs
Create a new training run.

**Request Body:**
```json
{
  "s3_bucket": "my-bucket",
  "num_workers": 5,
  "episodes_per_worker": 20,
  "update_steps": 100,
  "max_iterations": 10,
  "trace_path": "demo/traces/",
  "namespace": "virtual-default",
  "target": 3
}
```

### POST /runs/{run_id}/start
Start a pending training run.

### POST /runs/{run_id}/stop
Stop a running training run.

### GET /runs/{run_id}
Get details for a specific run.

## Configuration

The server uses the following environment variables:

- `AWS_REGION`: AWS region for EC2 and S3 operations
- `AWS_ACCESS_KEY_ID`: AWS access key
- `AWS_SECRET_ACCESS_KEY`: AWS secret key
- `S3_BUCKET`: Default S3 bucket (can be overridden per run)

## Database Schema

Runs are stored in a SQLite database (`training_runs.db`) with the following structure:

```sql
CREATE TABLE runs (
    run_id TEXT PRIMARY KEY,
    data TEXT  -- JSON-encoded TrainingRun dataclass
);
```

## Training Flow

1. **Create Run**: User submits run configuration via web form
2. **Start Run**: Server launches background thread for training loop
3. **Launch Workers**: For each iteration, launch EC2 instances via launch template
4. **Wait for Completion**: Poll S3 for worker completion markers
5. **Aggregate Data**: Download and merge experience data from all workers
6. **Update Model**: Perform DQN training steps on aggregated experiences
7. **Distribute Model**: Upload updated model to S3 for next iteration
8. **Cleanup**: Terminate workers and clean up old S3 data
9. **Repeat**: Continue until max iterations reached

## Error Handling

- Worker timeouts are handled with configurable timeout (default: 1 hour)
- Failed runs are marked with error status and message
- Background threads are daemon threads (exit when main process exits)
- S3 operations include retry logic via boto3

## Security Considerations

- No authentication/authorization implemented (add as needed)
- AWS credentials should be properly configured
- Server should run on secure network/internal access only
- Consider adding rate limiting for API endpoints

## Future Enhancements

- Authentication and user management
- Real-time progress updates via WebSockets
- Model versioning and rollback
- Integration with monitoring systems (CloudWatch, etc.)
- Batch job scheduling
- Multi-region support