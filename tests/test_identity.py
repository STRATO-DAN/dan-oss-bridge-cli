"""Regression tests for per-agent identity (HMAC-signed messages), added in 0.2.0.

Each test locks in one behaviour of the identity layer and fails against the pre-identity code
(there was no keyring, no signing, no verification, and post never required registration):

- register creates a 0600 keyring holding a key for the agent (idempotent; --rotate replaces it);
- a signed post from a registered agent reads back verified;
- a forged, tampered, or unsigned message reads back UNVERIFIED (and is never dropped);
- an unregistered agent cannot post while identity is on (deny-by-default on trust);
- DAN_OSS_BRIDGE_NO_AUTH=1 restores the original unauthenticated post and unflagged read;
- corrupt-line tolerance still holds with verification active.
"""

import io
import os
import stat
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.bus import MessageBus, UnregisteredAgentError            # noqa: E402
from dan_oss_bridge.cli import main                                          # noqa: E402
from dan_oss_bridge.keyring import Keyring                                   # noqa: E402


class KeyringRegistrationTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "agents.json"
        self.keyring = Keyring(self.path)

    def tearDown(self):
        self._tmp.cleanup()

    def test_register_creates_a_0600_keyring_with_a_key(self):
        self.assertTrue(self.keyring.register("agent-a"))
        self.assertTrue(self.path.is_file())
        mode = stat.S_IMODE(os.stat(self.path).st_mode)
        self.assertEqual(mode, 0o600, f"keyring must be 0600, got {oct(mode)}")
        key = self.keyring.get("agent-a")
        self.assertIsInstance(key, str)
        self.assertEqual(len(key), 64)  # 32 random bytes, hex-encoded
        bytes.fromhex(key)  # must be valid hex

    def test_register_is_idempotent_without_rotate(self):
        self.assertTrue(self.keyring.register("agent-a"))
        first = self.keyring.get("agent-a")
        self.assertFalse(self.keyring.register("agent-a"))  # no-op, returns False
        self.assertEqual(self.keyring.get("agent-a"), first)  # key unchanged

    def test_rotate_replaces_an_existing_key(self):
        self.keyring.register("agent-a")
        first = self.keyring.get("agent-a")
        self.assertTrue(self.keyring.register("agent-a", rotate=True))
        self.assertNotEqual(self.keyring.get("agent-a"), first)

    def test_registering_a_second_agent_keeps_the_first(self):
        self.keyring.register("agent-a")
        self.keyring.register("agent-b")
        self.assertIsNotNone(self.keyring.get("agent-a"))
        self.assertIsNotNone(self.keyring.get("agent-b"))


class SignedPostVerifyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus_path = Path(self._tmp.name) / "bus.jsonl"
        self.keyring = Keyring(Path(self._tmp.name) / "agents.json")
        self.keyring.register("agent-a")
        self.bus = MessageBus(self.bus_path, keyring=self.keyring)

    def tearDown(self):
        self._tmp.cleanup()

    def test_a_signed_post_verifies_on_read(self):
        self.bus.post("standup", "agent-a", "signed message")
        msgs = self.bus.read("standup")
        self.assertEqual(len(msgs), 1)
        self.assertTrue(msgs[0].verified)
        self.assertTrue(msgs[0].hmac)  # a signature was actually stored

    def test_an_unregistered_agent_cannot_post_by_default(self):
        with self.assertRaises(UnregisteredAgentError):
            self.bus.post("standup", "stranger", "should be rejected")
        # nothing was written
        self.assertEqual(self.bus.read("standup"), [])

    def test_a_message_from_an_unknown_agent_reads_unverified(self):
        # A message signed correctly for agent-a, but whose agent the reader has no key for.
        self.bus.post("standup", "agent-a", "hello")
        reader = MessageBus(self.bus_path, keyring=Keyring(Path(self._tmp.name) / "other.json"))
        msgs = reader.read("standup")
        self.assertEqual(len(msgs), 1)
        self.assertIs(msgs[0].verified, False)

    def test_a_tampered_text_reads_unverified(self):
        self.bus.post("standup", "agent-a", "original")
        # Rewrite the stored text but keep the old HMAC -> signature no longer matches.
        raw = self.bus_path.read_text(encoding="utf-8")
        self.bus_path.write_text(raw.replace("original", "tampered!"), encoding="utf-8")
        msgs = self.bus.read("standup")
        self.assertEqual(msgs[0].text, "tampered!")
        self.assertIs(msgs[0].verified, False)

    def test_an_old_unsigned_message_reads_unverified(self):
        # Simulate a pre-identity log line: a record with no hmac field.
        self.bus_path.parent.mkdir(parents=True, exist_ok=True)
        self.bus_path.write_text(
            '{"channel": "standup", "agent": "agent-a", "text": "legacy", "ts": 1.0}\n',
            encoding="utf-8",
        )
        msgs = self.bus.read("standup")
        self.assertEqual(msgs[0].text, "legacy")
        self.assertIs(msgs[0].verified, False)  # flagged, not dropped

    def test_rotating_a_key_makes_old_messages_unverified(self):
        self.bus.post("standup", "agent-a", "before rotate")
        self.assertTrue(self.bus.read("standup")[0].verified)
        self.keyring.register("agent-a", rotate=True)
        self.assertIs(self.bus.read("standup")[0].verified, False)

    def test_verification_tolerates_a_corrupt_line_among_signed_ones(self):
        self.bus.post("standup", "agent-a", "good one")
        with self.bus_path.open("a", encoding="utf-8") as f:
            f.write("not json at all\n")
            f.write("123\n")
        self.bus.post("standup", "agent-a", "good two")
        msgs = self.bus.read("standup")  # must not raise; corrupt lines skipped
        self.assertEqual([m.text for m in msgs], ["good one", "good two"])
        self.assertTrue(all(m.verified for m in msgs))


class NoKeyringModeTests(unittest.TestCase):
    """A bus with no keyring keeps the original unauthenticated behaviour."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus = MessageBus(Path(self._tmp.name) / "bus.jsonl")  # no keyring

    def tearDown(self):
        self._tmp.cleanup()

    def test_post_without_keyring_needs_no_registration_and_stores_no_hmac(self):
        self.bus.post("standup", "anyone", "unauthenticated")  # must not raise
        msgs = self.bus.read("standup")
        self.assertEqual(msgs[0].text, "unauthenticated")
        self.assertEqual(msgs[0].hmac, "")
        self.assertIsNone(msgs[0].verified)  # not checked


class CliIdentityTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus_path = str(Path(self._tmp.name) / "bus.jsonl")
        self.keyring_path = str(Path(self._tmp.name) / "agents.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args, env_no_auth=False):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        prev = os.environ.get("DAN_OSS_BRIDGE_NO_AUTH")
        if env_no_auth:
            os.environ["DAN_OSS_BRIDGE_NO_AUTH"] = "1"
        else:
            os.environ.pop("DAN_OSS_BRIDGE_NO_AUTH", None)
        try:
            with redirect_stdout(buf_out), redirect_stderr(buf_err):
                code = main(["--bus", self.bus_path, "--keyring", self.keyring_path, *args])
        finally:
            if prev is None:
                os.environ.pop("DAN_OSS_BRIDGE_NO_AUTH", None)
            else:
                os.environ["DAN_OSS_BRIDGE_NO_AUTH"] = prev
        return code, buf_out.getvalue(), buf_err.getvalue()

    def test_register_then_post_then_read_shows_verified(self):
        code, out, _ = self._run("register", "agent-a")
        self.assertEqual(code, 0)
        self.assertIn("registered agent 'agent-a'", out)
        # the secret key hex must never be printed to stdout
        key = Keyring(self.keyring_path).get("agent-a")
        self.assertNotIn(key, out)

        self._run("post", "standup", "agent-a", "hi there")
        code, out, _ = self._run("read", "standup")
        self.assertEqual(code, 0)
        self.assertIn("[standup] agent-a: hi there", out)
        self.assertNotIn("UNVERIFIED", out)

    def test_unregistered_agent_post_is_rejected_with_a_clear_error(self):
        code, _, err = self._run("post", "standup", "stranger", "nope")
        self.assertEqual(code, 2)
        self.assertIn("not registered", err)
        self.assertIn("register stranger", err)  # actionable hint
        self.assertNotIn("Traceback", err)

    def test_read_flags_an_unsigned_message_as_unverified(self):
        # Post while auth is off (no signature), then read with auth on.
        self._run("post", "standup", "ghost", "unsigned", env_no_auth=True)
        code, out, _ = self._run("read", "standup")
        self.assertEqual(code, 0)
        self.assertIn("[standup] ghost (UNVERIFIED): unsigned", out)

    def test_no_auth_env_restores_old_unauthenticated_post_and_unflagged_read(self):
        # Never registered anyone; with NO_AUTH the post succeeds and the read is not flagged.
        code, _, _ = self._run("post", "standup", "ghost", "free post", env_no_auth=True)
        self.assertEqual(code, 0)
        code, out, _ = self._run("read", "standup", env_no_auth=True)
        self.assertEqual(code, 0)
        self.assertIn("[standup] ghost: free post", out)
        self.assertNotIn("UNVERIFIED", out)

    def test_register_is_idempotent_via_cli(self):
        self._run("register", "agent-a")
        code, out, _ = self._run("register", "agent-a")
        self.assertEqual(code, 0)
        self.assertIn("already registered", out)
        code, out, _ = self._run("register", "agent-a", "--rotate")
        self.assertEqual(code, 0)
        self.assertIn("rotated key", out)


if __name__ == "__main__":
    unittest.main()
