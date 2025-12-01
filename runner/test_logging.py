import json
from pathlib import Path
import one_step

def test_write_step_record(tmp_path):
    # Redirect log directory to the tmp folder
    one_step.STEP_LOG = tmp_path / "step.jsonl"

    record = {"a": 1, "b": 2}
    one_step.write_step_record(record)

    # verify file written
    content = (tmp_path / "step.jsonl").read_text().splitlines()
    assert len(content) == 1
    assert json.loads(content[0]) == record


def test_update_summary(tmp_path):
    # redirect summary log
    one_step.SUMMARY_LOG = tmp_path / "summary.json"

    r1 = {"reward": 5}
    r2 = {"reward": 10}

    one_step.update_summary(r1)
    one_step.update_summary(r2)

    summary = json.loads(one_step.SUMMARY_LOG.read_text())

    assert summary["total_steps"] == 2
    assert summary["total_rewards"] == 15
    assert summary["steps"][0]["reward"] == 5
    assert summary["steps"][1]["reward"] == 10