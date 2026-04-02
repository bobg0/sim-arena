"""
Tests for the sim-arena worker protocol.

Covers:
  - JobManifest / JobResult serialization
  - s3_helpers utilities (s3_uri_to_bucket_key)
  - worker._ext_for_agent, worker._extract_metrics
  - worker.run_job (mocked subprocess + S3 helpers)
  - dispatch.submit_job / dispatch.list_jobs (mocked S3 helpers)

No actual AWS credentials or train.py execution required.
"""

import dataclasses
import json
import os
import sys
import shutil
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

# Make sure the project root is on the path so imports work
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.schemas import JobManifest, JobResult
from protocol.s3_helpers import s3_uri_to_bucket_key
from protocol.worker import (
    _ext_for_agent,
    _extract_metrics,
    _wait_for_server_weights,
    run_job,
)
from protocol.dispatch import submit_job, list_jobs


# ---------------------------------------------------------------------------
# Schema tests
# ---------------------------------------------------------------------------

class TestJobManifest:
    def test_defaults(self):
        m = JobManifest(job_id="j1", trace_s3_uri="s3://bucket/trace.msgpack")
        assert m.agent == "dqn"
        assert m.episodes == 10
        assert m.weights_s3_uri is None
        assert m.timeout_seconds == 3600

    def test_roundtrip_json(self):
        m = JobManifest(
            job_id="j1",
            trace_s3_uri="s3://bucket/trace.msgpack",
            agent="greedy",
            episodes=5,
        )
        restored = JobManifest.from_json(m.to_json())
        assert restored.job_id == "j1"
        assert restored.agent == "greedy"
        assert restored.episodes == 5
        assert restored.weights_s3_uri is None

    def test_from_dict_ignores_unknown_keys(self):
        d = dataclasses.asdict(
            JobManifest(job_id="j2", trace_s3_uri="s3://b/t.msgpack")
        )
        d["unknown_future_field"] = "should be ignored"
        m = JobManifest.from_dict(d)
        assert m.job_id == "j2"

    def test_with_weights(self):
        m = JobManifest(
            job_id="j3",
            trace_s3_uri="s3://b/t.msgpack",
            weights_s3_uri="s3://b/results/j0/checkpoint_final.pt",
        )
        restored = JobManifest.from_json(m.to_json())
        assert restored.weights_s3_uri == "s3://b/results/j0/checkpoint_final.pt"

    def test_per_episode_sync_defaults(self):
        m = JobManifest(job_id="j4", trace_s3_uri="s3://b/t.msgpack")
        assert m.per_episode_s3_sync is False
        assert m.sync_identity_server is False
        assert m.sync_weights_poll_interval_seconds == 30
        assert m.sync_server_weights_timeout_seconds == 7200

    def test_per_episode_sync_roundtrip_json(self):
        m = JobManifest(
            job_id="j5",
            trace_s3_uri="s3://b/t.msgpack",
            per_episode_s3_sync=True,
            sync_identity_server=True,
            sync_weights_poll_interval_seconds=5,
            sync_server_weights_timeout_seconds=60,
        )
        r = JobManifest.from_json(m.to_json())
        assert r.per_episode_s3_sync is True
        assert r.sync_identity_server is True
        assert r.sync_weights_poll_interval_seconds == 5
        assert r.sync_server_weights_timeout_seconds == 60

    def test_federation_fields_default(self):
        m = JobManifest(job_id="jf", trace_s3_uri="s3://b/t.msgpack")
        assert m.federation_group_id is None
        assert m.federation_size == 1

    def test_federation_roundtrip_json(self):
        m = JobManifest(
            job_id="jf2",
            trace_s3_uri="s3://b/t.msgpack",
            per_episode_s3_sync=True,
            federation_group_id="run-2026-04-03",
            federation_size=4,
        )
        r = JobManifest.from_json(m.to_json())
        assert r.federation_group_id == "run-2026-04-03"
        assert r.federation_size == 4


class TestJobResult:
    def _make(self, **kwargs):
        defaults = dict(
            job_id="j1",
            worker_id="w1",
            status="success",
            started_at="2026-01-01T00:00:00Z",
            finished_at="2026-01-01T00:10:00Z",
            elapsed_seconds=600.0,
        )
        defaults.update(kwargs)
        return JobResult(**defaults)

    def test_roundtrip_json(self):
        r = self._make(episodes_completed=5, total_reward=12.5, final_reward=3.1)
        restored = JobResult.from_json(r.to_json())
        assert restored.status == "success"
        assert restored.total_reward == 12.5
        assert restored.final_reward == 3.1

    def test_failed_result(self):
        r = self._make(status="failed", error="train.py exited with code 1")
        restored = JobResult.from_json(r.to_json())
        assert restored.status == "failed"
        assert "train.py" in restored.error

    def test_from_dict_ignores_unknown_keys(self):
        d = dataclasses.asdict(self._make())
        d["new_field"] = 99
        r = JobResult.from_dict(d)
        assert r.job_id == "j1"


# ---------------------------------------------------------------------------
# s3_helpers tests
# ---------------------------------------------------------------------------

class TestS3Helpers:
    def test_parse_standard_uri(self):
        b, k = s3_uri_to_bucket_key("s3://my-bucket/path/to/file.msgpack")
        assert b == "my-bucket"
        assert k == "path/to/file.msgpack"

    def test_parse_root_key(self):
        b, k = s3_uri_to_bucket_key("s3://bucket/file.pt")
        assert b == "bucket"
        assert k == "file.pt"

    def test_rejects_non_s3(self):
        with pytest.raises(ValueError):
            s3_uri_to_bucket_key("https://example.com/file")

    @patch("protocol.s3_helpers._client")
    def test_copy_object_calls_s3(self, mock_client_factory):
        mock_client = MagicMock()
        mock_client_factory.return_value = mock_client
        from protocol.s3_helpers import copy_object

        copy_object("my-bucket", "src/key.pt", "dst/key.pt")
        mock_client.copy_object.assert_called_once()
        call_kw = mock_client.copy_object.call_args.kwargs
        assert call_kw["Bucket"] == "my-bucket"
        assert call_kw["Key"] == "dst/key.pt"
        assert call_kw["CopySource"] == {"Bucket": "my-bucket", "Key": "src/key.pt"}


# ---------------------------------------------------------------------------
# worker helper tests
# ---------------------------------------------------------------------------

class TestWorkerHelpers:
    def test_ext_for_known_agents(self):
        assert _ext_for_agent("dqn") == ".pt"
        assert _ext_for_agent("greedy") == ".json"
        assert _ext_for_agent("random") == ".json"

    def test_ext_for_unknown_agent_defaults_to_pt(self):
        assert _ext_for_agent("future_agent") == ".pt"

    def test_extract_metrics_dqn(self, tmp_path):
        ckpt = tmp_path / "checkpoint_final.pt"
        import torch
        torch.save({"episode_reward_history": [1.0, 2.0, 3.0]}, str(ckpt))
        episodes, total, final = _extract_metrics(ckpt, "dqn")
        assert episodes == 3
        assert abs(total - 6.0) < 1e-4
        assert abs(final - 3.0) < 1e-4

    def test_extract_metrics_greedy(self, tmp_path):
        ckpt = tmp_path / "checkpoint_final.json"
        ckpt.write_text(json.dumps({"episode_reward_history": [10.0, 20.0]}))
        episodes, total, final = _extract_metrics(ckpt, "greedy")
        assert episodes == 2
        assert abs(total - 30.0) < 1e-4
        assert abs(final - 20.0) < 1e-4

    def test_extract_metrics_missing_file(self, tmp_path):
        missing = tmp_path / "no_file.pt"
        episodes, total, final = _extract_metrics(missing, "dqn")
        assert episodes == 0
        assert total is None
        assert final is None

    def test_extract_metrics_empty_history(self, tmp_path):
        ckpt = tmp_path / "checkpoint_final.json"
        ckpt.write_text(json.dumps({"episode_reward_history": []}))
        episodes, total, final = _extract_metrics(ckpt, "greedy")
        assert episodes == 0
        assert total is None


# ---------------------------------------------------------------------------
# worker.run_job integration (mocked subprocess + S3)
# ---------------------------------------------------------------------------

class TestRunJob:
    def _manifest(self, **kwargs):
        defaults = dict(
            job_id="test_job_001",
            trace_s3_uri="s3://diya-simarena-traces/demo/trace-mem-slight.msgpack",
            agent="greedy",
            episodes=2,
            steps=5,
            duration=10,
            timeout_seconds=120,
        )
        defaults.update(kwargs)
        return JobManifest(**defaults)

    def _fake_subprocess(self, save_path_container: list):
        """Returns a subprocess.run mock that writes a fake checkpoint."""
        def side_effect(cmd, **kwargs):
            # Extract the --save path from the command and write a fake checkpoint
            if "--save" in cmd:
                idx = cmd.index("--save")
                save_path = Path(cmd[idx + 1])
                save_path.parent.mkdir(parents=True, exist_ok=True)
                save_path.write_text(json.dumps({
                    "episode_reward_history": [5.0, 7.0],
                    "n_actions": 4,
                }))
                save_path_container.append(save_path)
            result = MagicMock()
            result.returncode = 0
            return result
        return side_effect

    @patch("protocol.worker.upload_file")
    @patch("protocol.worker.download_file")
    @patch("subprocess.run")
    def test_successful_job(self, mock_subproc, mock_download, mock_upload):
        save_path_container = []
        mock_subproc.side_effect = self._fake_subprocess(save_path_container)

        manifest = self._manifest()
        result = run_job(manifest, "worker-1", "diya-simarena-jobs")

        assert result.status == "success"
        assert result.job_id == "test_job_001"
        assert result.worker_id == "worker-1"
        assert result.episodes_completed == 2
        assert result.total_reward == pytest.approx(12.0)
        assert result.final_reward == pytest.approx(7.0)
        assert result.checkpoint_s3_uri is not None
        assert "test_job_001" in result.checkpoint_s3_uri
        mock_download.assert_not_called()  # no weights_s3_uri

    @patch("protocol.worker.upload_file")
    @patch("protocol.worker.download_file")
    @patch("subprocess.run")
    def test_job_with_weights(self, mock_subproc, mock_download, mock_upload):
        save_path_container = []
        mock_subproc.side_effect = self._fake_subprocess(save_path_container)

        manifest = self._manifest(
            weights_s3_uri="s3://diya-simarena-jobs/results/prev_job/checkpoint_final.json"
        )
        result = run_job(manifest, "worker-2", "diya-simarena-jobs")

        assert result.status == "success"
        mock_download.assert_called_once()
        # --load and --transfer flags should be in the command
        cmd_args = mock_subproc.call_args[0][0]
        assert "--load" in cmd_args
        assert "--transfer" in cmd_args

    @patch("protocol.worker.upload_file")
    @patch("subprocess.run")
    def test_failed_job_nonzero_exit(self, mock_subproc, mock_upload):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_subproc.return_value = mock_result

        manifest = self._manifest()
        result = run_job(manifest, "worker-1", "diya-simarena-jobs")

        assert result.status == "failed"
        assert "exited with code 1" in result.error

    @patch("subprocess.run")
    def test_timeout_job(self, mock_subproc):
        import subprocess
        mock_subproc.side_effect = subprocess.TimeoutExpired(cmd="train.py", timeout=5)

        manifest = self._manifest(timeout_seconds=5)
        result = run_job(manifest, "worker-1", "diya-simarena-jobs")

        assert result.status == "timeout"
        assert "Timed out" in result.error

    @patch("protocol.worker.put_json")
    @patch("protocol.worker.copy_object")
    @patch("protocol.worker.download_file")
    @patch("protocol.worker.upload_file")
    @patch("subprocess.run")
    def test_per_episode_sync_identity_two_episodes(
        self, mock_subproc, mock_upload, mock_download, mock_copy, mock_put
    ):
        """sync_identity_server echoes checkpoint; two train.py runs with --episodes 1."""
        tmp = Path(tempfile.mkdtemp())
        s3_shadow: dict[str, Path] = {}

        try:

            def upload_side(local_path: str, bucket: str, key: str):
                dest = tmp / key.replace("/", "__")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(local_path, dest)
                s3_shadow[key] = dest

            def download_side(bucket: str, key: str, local_path: str):
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s3_shadow[key], local_path)

            def copy_side(bucket: str, src_key: str, dst_key: str):
                dest = tmp / dst_key.replace("/", "__")
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s3_shadow[src_key], dest)
                s3_shadow[dst_key] = dest

            def download_side(bucket: str, key: str, local_path: str):
                Path(local_path).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(s3_shadow[key], local_path)

            mock_upload.side_effect = upload_side
            mock_download.side_effect = download_side
            mock_copy.side_effect = copy_side

            n_calls = [0]

            def subproc_side_effect(cmd, **kwargs):
                if "--save" in cmd:
                    idx = cmd.index("--save")
                    save_path = Path(cmd[idx + 1])
                    save_path.parent.mkdir(parents=True, exist_ok=True)
                    n_calls[0] += 1
                    save_path.write_text(
                        json.dumps({"episode_reward_history": [float(n_calls[0])]})
                    )
                result = MagicMock()
                result.returncode = 0
                return result

            mock_subproc.side_effect = subproc_side_effect

            manifest = JobManifest(
                job_id="sync_job_01",
                trace_s3_uri="s3://traces/demo/t.msgpack",
                agent="greedy",
                episodes=2,
                steps=3,
                duration=5,
                timeout_seconds=300,
                per_episode_s3_sync=True,
                sync_identity_server=True,
            )
            result = run_job(manifest, "worker-sync", "test-bucket")

            assert result.status == "success"
            assert result.episodes_completed == 2
            assert result.total_reward == pytest.approx(3.0)
            assert result.final_reward == pytest.approx(2.0)
            assert mock_subproc.call_count == 2
            cmds = [c[0][0] for c in mock_subproc.call_args_list]
            for cmd in cmds:
                assert cmd[cmd.index("--episodes") + 1] == "1"
            assert mock_copy.call_count == 1
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    @patch("protocol.worker.object_exists", return_value=False)
    @patch("protocol.worker.time.sleep", return_value=None)
    def test_wait_for_server_weights_timeout(self, _mock_sleep, _mock_exists):
        with pytest.raises(TimeoutError, match="Timed out"):
            _wait_for_server_weights("b", "k", poll_interval=1, timeout_seconds=0.01)


# ---------------------------------------------------------------------------
# dispatch tests
# ---------------------------------------------------------------------------

class TestDispatch:
    def _manifest(self):
        return JobManifest(
            job_id="dispatch_test_001",
            trace_s3_uri="s3://diya-simarena-traces/demo/trace-mem-slight.msgpack",
        )

    @patch("protocol.dispatch.put_json")
    def test_submit_job_writes_correct_key(self, mock_put):
        manifest = self._manifest()
        key = submit_job(manifest, "my-bucket")
        assert key == "jobs/pending/dispatch_test_001/manifest.json"
        mock_put.assert_called_once_with(
            "my-bucket",
            "jobs/pending/dispatch_test_001/manifest.json",
            dataclasses.asdict(manifest),
        )

    @patch("protocol.dispatch.get_json")
    @patch("protocol.dispatch.list_keys")
    def test_list_jobs_shows_done(self, mock_list, mock_get_json, capsys):
        mock_list.side_effect = lambda bucket, prefix: (
            ["jobs/pending/job_a/manifest.json"] if "pending" in prefix
            else (["results/job_b/result.json"] if "results" in prefix else [])
        )
        mock_get_json.return_value = {
            "job_id": "job_b",
            "worker_id": "w1",
            "status": "success",
            "started_at": "2026-01-01T00:00:00Z",
            "finished_at": "2026-01-01T00:10:00Z",
            "elapsed_seconds": 600.0,
            "episodes_completed": 5,
            "total_reward": 25.0,
            "final_reward": 6.0,
        }
        list_jobs("my-bucket")
        out = capsys.readouterr().out
        assert "job_a" in out
        assert "pending" in out
        assert "job_b" in out
        assert "success" in out
