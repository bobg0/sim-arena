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
