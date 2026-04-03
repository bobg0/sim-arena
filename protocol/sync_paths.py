"""
S3 key layout for per-episode weight sync (worker ↔ sync server).

Kept in one module so worker.py and sync_server.py cannot drift.
"""

CHECKPOINT_EXT = {"dqn": ".pt", "greedy": ".json", "random": ".json"}


def checkpoint_ext(agent: str) -> str:
    return CHECKPOINT_EXT.get(agent, ".pt")


def from_worker_ckpt_key(job_id: str, finished_ep: int, ext: str) -> str:
    return f"results/{job_id}/sync/from_worker/after_ep_{finished_ep:04d}/checkpoint{ext}"


def from_worker_done_key(job_id: str, finished_ep: int) -> str:
    return f"results/{job_id}/sync/from_worker/after_ep_{finished_ep:04d}/done.json"


def to_worker_weights_key(job_id: str, before_ep: int, ext: str) -> str:
    return f"results/{job_id}/sync/to_worker/before_ep_{before_ep:04d}/weights{ext}"


# --- Federated runs (multiple workers share one global model between episodes) ---

FEDERATION_PREFIX = "results/_federation"


def federation_from_ckpt_key(group_id: str, ep: int, worker_id: str, ext: str) -> str:
    return (
        f"{FEDERATION_PREFIX}/{group_id}/from_worker/after_ep_{ep:04d}/"
        f"{worker_id}/checkpoint{ext}"
    )


def federation_from_done_key(group_id: str, ep: int, worker_id: str) -> str:
    return (
        f"{FEDERATION_PREFIX}/{group_id}/from_worker/after_ep_{ep:04d}/"
        f"{worker_id}/done.json"
    )


def federation_global_weights_key(group_id: str, before_ep: int, ext: str) -> str:
    """Single checkpoint all workers download before starting episode `before_ep`."""
    return (
        f"{FEDERATION_PREFIX}/{group_id}/to_worker/before_ep_{before_ep:04d}/global_weights{ext}"
    )
