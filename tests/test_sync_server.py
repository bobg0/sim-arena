"""Tests for protocol/sync_server.py and protocol/sync_paths.py (no AWS calls)."""

import shutil
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import torch

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.sync_paths import (
    checkpoint_ext,
    federation_from_ckpt_key,
    federation_global_weights_key,
    from_worker_ckpt_key,
    from_worker_done_key,
    to_worker_weights_key,
)
from protocol.sync_server import DONE_KEY_RE, FED_DONE_RE, process_bucket_once


class TestSyncPaths:
    def test_keys(self):
        assert from_worker_ckpt_key("j1", 1, ".pt") == "results/j1/sync/from_worker/after_ep_0001/checkpoint.pt"
        assert from_worker_done_key("j1", 2) == "results/j1/sync/from_worker/after_ep_0002/done.json"
        assert to_worker_weights_key("j1", 3, ".json") == "results/j1/sync/to_worker/before_ep_0003/weights.json"

    def test_checkpoint_ext(self):
        assert checkpoint_ext("dqn") == ".pt"
        assert checkpoint_ext("greedy") == ".json"

    def test_federation_keys(self):
        assert "g9" in federation_from_ckpt_key("g9", 1, "w1", ".pt")
        assert federation_global_weights_key("g9", 2, ".pt").endswith(
            "before_ep_0002/global_weights.pt"
        )


class TestDoneKeyRegex:
    def test_matches(self):
        m = DONE_KEY_RE.match("results/job_x/sync/from_worker/after_ep_0007/done.json")
        assert m
        assert m.group("job_id") == "job_x"
        assert int(m.group("ep")) == 7


class TestFedDoneKeyRegex:
    def test_matches(self):
        m = FED_DONE_RE.match(
            "results/_federation/mygrp/from_worker/after_ep_0001/i-0abc/done.json"
        )
        assert m
        assert m.group("gid") == "mygrp"
        assert int(m.group("ep")) == 1
        assert m.group("wid") == "i-0abc"


class TestProcessBucketOnce:
    @patch("protocol.sync_server.copy_object")
    @patch("protocol.sync_server.object_exists")
    @patch("protocol.sync_server.get_json")
    @patch("protocol.sync_server.list_keys")
    def test_copies_when_barrier_missing(
        self, mock_list, mock_get_json, mock_exists, mock_copy
    ):
        done_key = "results/job_a/sync/from_worker/after_ep_0001/done.json"
        src_key = "results/job_a/sync/from_worker/after_ep_0001/checkpoint.pt"
        dst_key = "results/job_a/sync/to_worker/before_ep_0002/weights.pt"

        def list_side_effect(bucket, prefix):
            if prefix == "results/_federation/":
                return []
            return [done_key, src_key]

        mock_list.side_effect = list_side_effect

        def exists_side_effect(bucket, key):
            return key in (done_key, src_key)

        mock_exists.side_effect = exists_side_effect
        mock_get_json.return_value = {
            "job_id": "job_a",
            "agent": "dqn",
            "total_episodes": 3,
            "episode_index": 1,
        }

        n = process_bucket_once("bkt")
        assert n == 1
        mock_copy.assert_called_once_with("bkt", src_key, dst_key)

    @patch("protocol.sync_server.copy_object")
    @patch("protocol.sync_server.object_exists")
    @patch("protocol.sync_server.get_json")
    @patch("protocol.sync_server.list_keys")
    def test_skips_final_episode(self, mock_list, mock_get_json, mock_exists, mock_copy):
        done_key = "results/job_a/sync/from_worker/after_ep_0003/done.json"

        def list_side_effect(bucket, prefix):
            if prefix == "results/_federation/":
                return []
            return [done_key]

        mock_list.side_effect = list_side_effect
        mock_exists.return_value = True
        mock_get_json.return_value = {
            "agent": "dqn",
            "total_episodes": 3,
            "episode_index": 3,
        }
        n = process_bucket_once("bkt")
        assert n == 0
        mock_copy.assert_not_called()

    @patch("protocol.sync_server.copy_object")
    @patch("protocol.sync_server.object_exists")
    @patch("protocol.sync_server.get_json")
    @patch("protocol.sync_server.list_keys")
    @patch("protocol.sync_server._total_episodes_from_manifest", return_value=5)
    def test_fallback_manifest_total(
        self, mock_manifest, mock_list, mock_get_json, mock_exists, mock_copy
    ):
        done_key = "results/job_b/sync/from_worker/after_ep_0001/done.json"
        src_key = "results/job_b/sync/from_worker/after_ep_0001/checkpoint.json"
        dst_key = "results/job_b/sync/to_worker/before_ep_0002/weights.json"
        def list_side_effect(bucket, prefix):
            if prefix == "results/_federation/":
                return []
            return [done_key, src_key]

        mock_list.side_effect = list_side_effect

        def exists_side_effect(bucket, key):
            return key in (done_key, src_key)

        mock_exists.side_effect = exists_side_effect
        mock_get_json.return_value = {"agent": "greedy", "episode_index": 1}

        n = process_bucket_once("bkt")
        assert n == 1
        mock_manifest.assert_called_once_with("bkt", "job_b")
        mock_copy.assert_called_once_with("bkt", src_key, dst_key)


class TestFederationSync:
    def _minimal_pt(self, path: Path, bias: float):
        q = torch.nn.Linear(2, 2)
        t = torch.nn.Linear(2, 2)
        torch.nn.init.constant_(q.bias, bias)
        ck = {
            "q_net_state_dict": q.state_dict(),
            "target_net_state_dict": t.state_dict(),
            "optimizer_state_dict": {},
            "total_steps": 0,
            "reward_history": [],
            "loss_history": [],
            "episode_reward_history": [bias],
            "current_episode_reward": bias,
            "hyperparams": {},
        }
        torch.save(ck, path)

    @patch("protocol.sync_server.upload_file")
    @patch("protocol.sync_server.download_file")
    @patch("protocol.sync_server.object_exists")
    @patch("protocol.sync_server.get_json")
    @patch("protocol.sync_server.list_keys")
    def test_federation_fedavg_publishes_global_weights(
        self, mock_list, mock_get_json, mock_exists, mock_download, mock_upload, tmp_path
    ):
        from protocol import sync_server as ss

        p1 = tmp_path / "w1.pt"
        p2 = tmp_path / "w2.pt"
        self._minimal_pt(p1, 1.0)
        self._minimal_pt(p2, 3.0)

        done1 = "results/_federation/g1/from_worker/after_ep_0001/worker-a/done.json"
        done2 = "results/_federation/g1/from_worker/after_ep_0001/worker-b/done.json"
        ck1 = "results/_federation/g1/from_worker/after_ep_0001/worker-a/checkpoint.pt"
        ck2 = "results/_federation/g1/from_worker/after_ep_0001/worker-b/checkpoint.pt"
        fed_keys = [done1, done2, ck1, ck2]

        def list_side_effect(bucket, prefix):
            if prefix == "results/_federation/":
                return fed_keys
            return []

        mock_list.side_effect = list_side_effect

        mock_get_json.return_value = {
            "agent": "dqn",
            "federation_size": 2,
            "total_episodes": 2,
            "federation_group_id": "g1",
            "episode_index": 1,
        }

        global_dst = federation_global_weights_key("g1", 2, ".pt")

        def exists_side_effect(bucket, key):
            if key == global_dst:
                return False
            return True

        mock_exists.side_effect = exists_side_effect

        def dl(bucket, key, local_path):
            if "worker-a" in key:
                shutil.copy(p1, local_path)
            else:
                shutil.copy(p2, local_path)

        mock_download.side_effect = dl

        n = ss._process_federation_sync("bkt")
        assert n == 1
        mock_upload.assert_called_once()
        up_args = mock_upload.call_args[0]
        assert up_args[2] == federation_global_weights_key("g1", 2, ".pt")
