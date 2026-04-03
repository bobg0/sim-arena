"""
Job manifest and result payload schemas for the sim-arena worker protocol.

Flow:
  1. dispatch.py writes a JobManifest to S3 (jobs/pending/<job_id>/manifest.json)
  2. worker.py picks it up, runs train.py, uploads checkpoint + log
  3. worker.py writes a JobResult to S3 (results/<job_id>/result.json)
  4. Central server (Task 3) reads result.json to collect weights and metrics
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class JobManifest:
    """What the central server sends to a worker."""

    job_id: str
    trace_s3_uri: str

    # "training" runs train.py; "experience_collection" uses runner/dist_run.py (when implemented)
    job_type: str = "training"

    # train.py arguments
    agent: str = "dqn"
    episodes: int = 10
    steps: int = 20
    duration: int = 40
    namespace: str = "default"
    deploy: str = "web"
    target: int = 3

    # Optional: S3 URI of initial weights file (.pt for dqn, .json for greedy/random).
    # None means start fresh. Pass the central server's latest weights here each round.
    weights_s3_uri: Optional[str] = None

    # Max wall-clock seconds the worker allows train.py to run before killing it
    timeout_seconds: int = 3600

<<<<<<< HEAD
=======
    # When True: after each episode the worker uploads checkpoint + metrics to S3, then
    # blocks until the central server (Task 3) writes the next weights under
    # results/<job_id>/sync/to_worker/before_ep_XXXX/weights.{pt|json} before starting
    # the next episode. See docs/WORKER_PROTOCOL.md § Per-episode S3 sync.
    per_episode_s3_sync: bool = False

    # Seconds between polls while waiting for server weights (per-episode sync only).
    sync_weights_poll_interval_seconds: int = 30

    # Max seconds to wait at each barrier for server-provided weights before failing the job.
    sync_server_weights_timeout_seconds: int = 7200

    # Dev/test: after each episode, copy the worker checkpoint into the next episode's
    # `to_worker` key (simulates the server echoing weights back without Task 3).
    sync_identity_server: bool = False

    # Federated learning: all jobs with the same non-empty federation_group_id share one
    # global model between episodes. Each worker uploads under results/_federation/<group>/...
    # sync_server.py waits for federation_size submissions, runs FedAvg (DQN .pt only),
    # then writes global_weights for the next episode. Requires per_episode_s3_sync=True.
    federation_group_id: Optional[str] = None
    federation_size: int = 1

>>>>>>> 9e57c0a58d1f237a151c563072078757a87c2a1d
    created_at: str = field(default_factory=_now_iso)

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "JobManifest":
        return cls(**json.loads(s))

    @classmethod
    def from_dict(cls, d: dict) -> "JobManifest":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class JobResult:
    """What the worker writes back after a job finishes (success or failure)."""

    job_id: str
    worker_id: str
    status: str  # "success" | "failed" | "timeout"
    started_at: str
    finished_at: str
    elapsed_seconds: float

    episodes_completed: int = 0
    total_reward: Optional[float] = None
    final_reward: Optional[float] = None

    error: Optional[str] = None

    # S3 URIs the central server should pull from
    checkpoint_s3_uri: Optional[str] = None
    log_s3_uri: Optional[str] = None
    transitions_s3_uri: Optional[str] = None

    def to_json(self) -> str:
        return json.dumps(asdict(self), indent=2)

    @classmethod
    def from_json(cls, s: str) -> "JobResult":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in json.loads(s).items() if k in known})

    @classmethod
    def from_dict(cls, d: dict) -> "JobResult":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})
