"""Sealed HMAC (v2): chain position bound into the signature, history preserved.

- A chained+signed post seals its chain position: copying the record to a later tail fails
  verification (its stored prev no longer matches) instead of verifying a second time.
- Every pre-seal signature (v1 canonical bytes, chained or not) verifies exactly as before —
  the format change bricks nothing.
- A replayed v1 record still verifies (documented residual: v1 predates position binding) and
  is counted as a duplicate; a replayed sealed record is forged.
- Non-strict verify says "local-trust only" on the verdict line when unsigned records exist.
"""
import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.bus import MessageBus
from dan_oss_bridge.keyring import Keyring, sign as key_sign
from dan_oss_bridge.verify import verify_log, format_report


class SealedHmacTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)
        self.kr = Keyring(self.dir / "agents.json")
        self.kr.register("alice")

    def tearDown(self):
        self._tmp.cleanup()

    def _chained_bus(self):
        return MessageBus(self.dir / "bus.jsonl", keyring=self.kr, chain=True)

    def test_sealed_post_verifies_ok_and_chain_intact(self):
        bus = self._chained_bus()
        bus.post("c", "alice", "hello")
        bus.post("c", "alice", "again")
        report = verify_log(bus.path, self.kr)
        self.assertTrue(report.chain_intact)
        self.assertEqual(report.forged, 0)
        self.assertEqual(report.ok, 2)

    def test_legacy_chained_signature_still_verifies(self):
        # A 0.3.0-era record: v1 MAC (no position binding) alongside a real prev link.
        bus = self._chained_bus()
        key = self.kr.get("alice")
        line = json.dumps({
            "channel": "c", "agent": "alice", "text": "legacy",
            "ts": 1700000000.0,
            "hmac": key_sign(key, "c", "alice", "legacy", 1700000000.0),
            "prev": "GENESIS",
        }) + "\n"
        bus.path.write_text(line, encoding="utf-8")
        report = verify_log(bus.path, self.kr)
        self.assertEqual(report.ok, 1)
        self.assertEqual(report.forged, 0)

    def test_replayed_sealed_record_is_forged_at_new_tail(self):
        # The real Finding-01 attack: copy a valid record, RE-POINT its prev at the current tip,
        # append without touching the signature. v1 would verify; sealed must fail.
        from dan_oss_bridge.chain import link_hash
        bus = self._chained_bus()
        bus.post("c", "alice", "first")
        bus.post("c", "alice", "second")
        lines = bus.path.read_text(encoding="utf-8").splitlines()
        first = json.loads(lines[0])
        last = json.loads(lines[-1])
        tip = link_hash(
            last.get("prev", ""), last["channel"], last["agent"],
            last["text"], last["ts"], last.get("hmac", ""),
        )
        forged_copy = dict(first, prev=tip)
        with bus.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(forged_copy) + "\n")
        report = verify_log(bus.path, self.kr)
        tail = report.records[-1]
        self.assertEqual(tail.auth, "forged", "a sealed record re-pointed at a new tail must fail HMAC")
        self.assertEqual(report.forged, 1)
        self.assertEqual(report.ok, 2, "the two genuine records still verify — no history bricked")

    def test_verbatim_copy_breaks_chain_but_keeps_hmac(self):
        # A byte-identical copy carries its prev along: HMAC still verifies (it is the same
        # record), but the chain breaks at the new position and the duplicate counter fires.
        bus = self._chained_bus()
        bus.post("c", "alice", "first")
        bus.post("c", "alice", "second")
        lines = bus.path.read_text(encoding="utf-8").splitlines()
        with bus.path.open("a", encoding="utf-8") as f:
            f.write(lines[0] + "\n")
        report = verify_log(bus.path, self.kr)
        self.assertEqual(report.replayed, 1)
        self.assertFalse(report.chain_intact)

    def test_replayed_v1_record_still_verifies_and_counts_as_duplicate(self):
        # Documented residual: v1 signatures predate position binding, so a copied v1 record
        # verifies — and is flagged as a possible replay by the duplicate detector.
        bus = MessageBus(self.dir / "bus.jsonl", keyring=self.kr, chain=False)
        bus.post("c", "alice", "once")
        lines = bus.path.read_text(encoding="utf-8").splitlines()
        with bus.path.open("a", encoding="utf-8") as f:
            f.write(lines[0] + "\n")
        report = verify_log(bus.path, self.kr)
        self.assertEqual(report.ok, 2)
        self.assertEqual(report.replayed, 1)

    def test_unchained_signature_is_byte_identical_v1(self):
        import hashlib
        import hmac as hmac_mod
        import json as json_mod
        key = self.kr.get("alice")
        got = key_sign(key, "c", "alice", "t", 1.5)
        want = hmac_mod.new(
            bytes.fromhex(key),
            json_mod.dumps(["c", "alice", "t", 1.5], separators=(",", ":"), ensure_ascii=False).encode("utf-8", "surrogatepass"),
            hashlib.sha256,
        ).hexdigest()
        self.assertEqual(got, want)

    def test_nonstrict_verdict_names_unsigned_records(self):
        bus = MessageBus(self.dir / "bus.jsonl")  # no keyring: unsigned local-trust mode
        bus.post("c", "alice", "plain")
        report = verify_log(bus.path, None)
        text = format_report(report, strict=False)
        self.assertIn("local-trust only", text)
        self.assertIn("unsigned", text)


if __name__ == "__main__":
    unittest.main()
