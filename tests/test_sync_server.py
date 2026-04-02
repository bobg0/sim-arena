"""Tests for protocol/sync_server.py and protocol/sync_paths.py (no AWS calls)."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from protocol.sync_paths import (
    checkpoint_ext,
    from_worker_ckpt_key,
    from_worker_done_key,
    to_worker_weights_key,
)
from protocol.sync_server import DONE_KEY_RE, process_bucket_once


class TestSyncPaths:
    def test_keys(self):
        assert from_worker_ckpt_key("j1", 1, ".pt") == "results/j1/sync/from_worker/after_ep_0001/checkpoint.pt"
        assert from_worker_done_key("j1", 2) == "results/j1/sync/from_worker/after_ep_0002/done.json"
        assert to_worker_weights_key("j1", 3, ".json") == "results/j1/sync/to_worker/before_ep_0003/weights.json"

    def test_checkpoint_ext(self):
        assert checkpoint_ext("dqn") == ".pt"
        assert checkpoint_ext("greedy") == ".json"


class TestDoneKeyRegex:
    def test_matches(self):
        m = DONE_KEY_RE.match("results/job_x/sync/from_worker/after_ep_0007/done.json")
        assert m
        assert m.group("job_id") == "job_x"
        assert int(m.group("ep")) == 7


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

        mock_list.return_value = [done_key, src_key]

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
        mock_list.return_value = [done_key]
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
        mock_list.return_value = [done_key, src_key]

        def exists_side_effect(bucket, key):
            return key in (done_key, src_key)

        mock_exists.side_effect = exists_side_effect
        mock_get_json.return_value = {"agent": "greedy", "episode_index": 1}

        n = process_bucket_once("bkt")
        assert n == 1
        mock_manifest.assert_called_once_with("bkt", "job_b")
        mock_copy.assert_called_once_with("bkt", src_key, dst_key)
