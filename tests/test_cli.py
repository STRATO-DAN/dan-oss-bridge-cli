"""Tests for dan_oss_bridge.cli — the real CLI end-to-end."""

import io
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.cli import main                                           # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus_path = str(Path(self._tmp.name) / "bus.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--bus", self.bus_path, *args])
        return code, buf.getvalue()

    def test_a_real_post_then_read_round_trip_via_the_cli(self):
        code, _ = self._run("post", "standup", "agent-a", "a real message")
        self.assertEqual(code, 0)
        code, out = self._run("read", "standup")
        self.assertEqual(code, 0)
        self.assertIn("a real message", out)

    def test_reading_an_empty_real_channel_says_so_honestly(self):
        code, out = self._run("read", "empty-channel")
        self.assertEqual(code, 0)
        self.assertIn("no real messages yet", out)

    def test_channels_lists_real_posted_channels(self):
        self._run("post", "alpha", "x", "1")
        code, out = self._run("channels")
        self.assertEqual(code, 0)
        self.assertIn("alpha", out)


if __name__ == "__main__":
    unittest.main()
