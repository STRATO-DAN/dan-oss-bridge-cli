"""Tests for dan_oss_bridge.cli — the real CLI end-to-end.

Per-agent identity is on by default (0.2.0), so these drive the CLI with a temp keyring and
register agents before they post. The identity-specific behaviour lives in test_identity.py.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge import __version__                                        # noqa: E402
from dan_oss_bridge.cli import main                                           # noqa: E402


class CliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus_path = str(Path(self._tmp.name) / "bus.jsonl")
        self.keyring_path = str(Path(self._tmp.name) / "agents.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = main(["--bus", self.bus_path, "--keyring", self.keyring_path, *args])
        return code, buf.getvalue()

    def test_a_real_post_then_read_round_trip_via_the_cli(self):
        self._run("register", "agent-a")
        code, _ = self._run("post", "standup", "agent-a", "a real message")
        self.assertEqual(code, 0)
        code, out = self._run("read", "standup")
        self.assertEqual(code, 0)
        self.assertIn("a real message", out)
        # a signed post from a registered agent reads back verified, not flagged.
        self.assertNotIn("UNVERIFIED", out)

    def test_reading_an_empty_real_channel_says_so_honestly(self):
        code, out = self._run("read", "empty-channel")
        self.assertEqual(code, 0)
        self.assertIn("no real messages yet", out)

    def test_channels_lists_real_posted_channels(self):
        self._run("register", "x")
        self._run("post", "alpha", "x", "1")
        code, out = self._run("channels")
        self.assertEqual(code, 0)
        self.assertIn("alpha", out)

    def test_read_json_emits_a_parseable_array_of_message_objects(self):
        self._run("register", "agent-a")
        self._run("post", "standup", "agent-a", "a real message")
        code, out = self._run("read", "standup", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)  # must be valid JSON
        self.assertIsInstance(data, list)
        self.assertEqual(len(data), 1)
        rec = data[0]
        self.assertEqual(rec["channel"], "standup")
        self.assertEqual(rec["agent"], "agent-a")
        self.assertEqual(rec["text"], "a real message")
        self.assertIn("ts", rec)
        # signed post from a registered agent -> verified true under default identity.
        self.assertTrue(rec["verified"])

    def test_read_json_on_an_empty_channel_is_an_empty_array_not_prose(self):
        code, out = self._run("read", "empty-channel", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])
        self.assertNotIn("no real messages", out)

    def test_channels_json_emits_a_parseable_list_of_names(self):
        self._run("register", "x")
        self._run("post", "alpha", "x", "1")
        self._run("post", "beta", "x", "2")
        code, out = self._run("channels", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertIsInstance(data, list)
        self.assertIn("alpha", data)
        self.assertIn("beta", data)

    def test_channels_json_on_an_empty_bus_is_an_empty_list(self):
        code, out = self._run("channels", "--json")
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(out), [])

    def test_version_flag_prints_the_package_version_and_exits_zero(self):
        buf = io.StringIO()
        with self.assertRaises(SystemExit) as cm:
            with redirect_stdout(buf):
                main(["--version"])
        self.assertEqual(cm.exception.code, 0)
        self.assertIn(__version__, buf.getvalue())

    def test_cli9_a_bus_path_that_is_a_directory_gives_a_friendly_error(self):
        # --bus pointing at a directory used to surface a raw IsADirectoryError traceback.
        self._run("register", "a")  # register so post reaches the bus and hits the path error
        dir_path = str(Path(self._tmp.name))  # the temp dir itself, not a file inside it
        buf_out, buf_err = io.StringIO(), io.StringIO()
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = main(["--bus", dir_path, "--keyring", self.keyring_path, "post", "c", "a", "hi"])
        self.assertEqual(code, 2)
        self.assertIn("error:", buf_err.getvalue())
        self.assertNotIn("Traceback", buf_err.getvalue())


if __name__ == "__main__":
    unittest.main()
