"""Regression tests for the mythos-audit hardening fixes (CLI3..CLI9).

Every test here FAILS against the pre-fix bus.py and PASSES after. They lock in corrupt-file
tolerance (a single bad line can never deny reads to every agent), the limit<=0 clamp, the
tail-read (read is no longer O(total file)), fsync-on-post durability, and the per-message text
cap — without regressing the SOLID append-only, lossless, ordered behaviour the original suite
covers.
"""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge import bus as bus_mod                                     # noqa: E402
from dan_oss_bridge.bus import MessageBus, MAX_TEXT_BYTES                     # noqa: E402


class CorruptFileToleranceTests(unittest.TestCase):
    """CLI3 / CLI4 / CLI5 — one bad line must never deny reads to every agent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"
        self.bus = MessageBus(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def _seed_good(self):
        self.bus.post("standup", "agent-a", "good message one")
        self.bus.post("standup", "agent-b", "good message two")

    def test_cli3_valid_json_but_non_dict_lines_are_skipped_not_crashing(self):
        # 123 / "x" / [...] are valid JSON but have no .get -> AttributeError on old code.
        self._seed_good()
        with self.path.open("a", encoding="utf-8") as f:
            f.write("123\n")
            f.write('"x"\n')
            f.write("[1, 2, 3]\n")
        msgs = self.bus.read("standup")  # must not raise
        self.assertEqual([m.text for m in msgs], ["good message one", "good message two"])
        # channels() walks the whole file — must also tolerate the non-dict lines.
        self.assertEqual(self.bus.channels(), ["standup"])

    def test_cli4_non_numeric_ts_does_not_crash_the_read(self):
        # float("not-a-number") -> ValueError on old code, denying every read.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write('{"channel": "c", "agent": "a", "text": "bad ts", "ts": "not-a-number"}\n')
        self.bus.post("c", "a", "good ts")
        msgs = self.bus.read("c")  # must not raise
        self.assertEqual([m.text for m in msgs], ["bad ts", "good ts"])
        # the bad-ts message survives with a defaulted timestamp, not dropped
        self.assertEqual(msgs[0].ts, 0.0)

    def test_cli5_one_invalid_utf8_byte_does_not_deny_the_whole_bus(self):
        # A single 0xFF byte made read_text() raise UnicodeDecodeError before any per-line
        # handling — a permanent read denial for read() AND channels().
        self._seed_good()
        with self.path.open("ab") as f:
            f.write(b"\xff\xfe not valid utf-8 line\n")
        self.bus.post("standup", "agent-c", "good message three")
        texts = [m.text for m in self.bus.read("standup")]
        self.assertIn("good message one", texts)
        self.assertIn("good message three", texts)
        self.assertEqual(self.bus.channels(), ["standup"])  # channels() tolerant too


class LimitClampTests(unittest.TestCase):
    """CLI7 — limit<=0 must return nothing, not everything / a front-drop."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus = MessageBus(Path(self._tmp.name) / "bus.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli7_limit_zero_returns_nothing(self):
        for i in range(5):
            self.bus.post("c", "x", f"msg{i}")
        self.assertEqual(self.bus.read("c", limit=0), [])       # was: returned everything

    def test_cli7_negative_limit_returns_nothing(self):
        for i in range(5):
            self.bus.post("c", "x", f"msg{i}")
        self.assertEqual(self.bus.read("c", limit=-2), [])      # was: dropped from the front


class TailReadTests(unittest.TestCase):
    """CLI6 — read(limit=N) reads the tail, not the entire file via read_text()."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus = MessageBus(Path(self._tmp.name) / "bus.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli6_read_does_not_load_whole_file_via_read_text(self):
        for i in range(200):
            self.bus.post("c", "x", f"msg{i}")

        original = Path.read_text

        def _boom(*a, **k):  # pragma: no cover - only fires on regression
            raise AssertionError("read() must not slurp the whole file via read_text()")

        Path.read_text = _boom
        try:
            msgs = self.bus.read("c", limit=3)
        finally:
            Path.read_text = original
        self.assertEqual([m.text for m in msgs], ["msg197", "msg198", "msg199"])

    def test_cli6_tail_read_is_correct_across_chunk_boundaries(self):
        # Force many small chunks so lines straddle chunk boundaries in the reverse reader.
        original = bus_mod._TAIL_CHUNK
        bus_mod._TAIL_CHUNK = 8
        try:
            for i in range(50):
                self.bus.post("c", "x", f"message-number-{i:03d}")
            msgs = self.bus.read("c", limit=4)
        finally:
            bus_mod._TAIL_CHUNK = original
        self.assertEqual(
            [m.text for m in msgs],
            ["message-number-046", "message-number-047",
             "message-number-048", "message-number-049"],
        )


class DurabilityAndCapTests(unittest.TestCase):
    """CLI8 (fsync durability) and CLI9 (text cap)."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus = MessageBus(Path(self._tmp.name) / "bus.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_cli8_post_flushes_and_fsyncs_best_effort(self):
        calls = []
        import os as _os
        original = _os.fsync
        _os.fsync = lambda fd: calls.append(fd)
        try:
            self.bus.post("c", "a", "durable")
        finally:
            _os.fsync = original
        self.assertEqual(len(calls), 1)  # post() fsyncs the appended line

    def test_cli9_oversize_text_is_rejected_with_a_clear_error(self):
        too_big = "x" * (MAX_TEXT_BYTES + 1)
        with self.assertRaises(ValueError):
            self.bus.post("c", "a", too_big)
        # a message right at the cap is still accepted
        self.bus.post("c", "a", "y" * MAX_TEXT_BYTES)
        self.assertEqual(len(self.bus.read("c")), 1)


if __name__ == "__main__":
    unittest.main()
