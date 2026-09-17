"""Tests for dan_oss_bridge.bus — real, standalone multi-channel message bus."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.bus import MessageBus                                     # noqa: E402


class MessageBusTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus = MessageBus(Path(self._tmp.name) / "bus.jsonl")

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_real_posted_message_is_read_back_on_its_own_real_channel(self):
        self.bus.post("standup", "agent-a", "starting real work")
        msgs = self.bus.read("standup")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].agent, "agent-a")
        self.assertEqual(msgs[0].text, "starting real work")

    def test_two_real_different_channels_stay_fully_independent(self):
        self.bus.post("standup", "agent-a", "standup message")
        self.bus.post("random", "agent-a", "random message")
        self.assertEqual(len(self.bus.read("standup")), 1)
        self.assertEqual(len(self.bus.read("random")), 1)
        self.assertEqual(self.bus.read("standup")[0].text, "standup message")

    def test_reading_with_no_channel_reads_every_real_channel(self):
        self.bus.post("a", "x", "1")
        self.bus.post("b", "x", "2")
        self.assertEqual(len(self.bus.read()), 2)

    def test_real_ordering_is_oldest_first_matching_a_real_chat_log(self):
        self.bus.post("c", "x", "first")
        self.bus.post("c", "x", "second")
        msgs = self.bus.read("c")
        self.assertEqual([m.text for m in msgs], ["first", "second"])

    def test_channels_lists_every_real_channel_that_has_ever_received_a_post(self):
        self.bus.post("alpha", "x", "1")
        self.bus.post("beta", "x", "2")
        self.assertEqual(set(self.bus.channels()), {"alpha", "beta"})

    def test_reading_an_empty_real_bus_returns_a_real_empty_list_not_an_error(self):
        self.assertEqual(self.bus.read(), [])

    def test_posting_without_a_real_channel_is_rejected(self):
        with self.assertRaises(ValueError):
            self.bus.post("", "agent", "text")

    def test_real_persistence_actually_survives_a_fresh_bus_instance(self):
        self.bus.post("c", "x", "persisted")
        reopened = MessageBus(self.bus.path)
        self.assertEqual(reopened.read("c")[0].text, "persisted")

    def test_the_real_limit_argument_actually_caps_what_read_returns(self):
        for i in range(5):
            self.bus.post("c", "x", f"msg{i}")
        self.assertEqual(len(self.bus.read("c", limit=2)), 2)
        # real, most-recent-within-the-window, not an arbitrary truncation from the front
        self.assertEqual(self.bus.read("c", limit=2)[-1].text, "msg4")


if __name__ == "__main__":
    unittest.main()
