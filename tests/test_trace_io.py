from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from env.actions.trace_io import load_trace, save_trace


class TraceIOTestCase(unittest.TestCase):
    def test_round_trip(self) -> None:
        payload = {"version": 1, "events": []}
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "trace.msgpack"
            save_trace(payload, dst)
            loaded = load_trace(dst)
        self.assertEqual(loaded, payload)

    def test_missing_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "nope.msgpack"
            with self.assertRaises(FileNotFoundError):
                load_trace(missing)


if __name__ == "__main__":  # pragma: no cover
    unittest.main()

