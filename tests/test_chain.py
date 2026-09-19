"""Tests for the hash chain + `verify` audit (0.3.0).

Each test locks in one property and fails against the pre-0.3.0 code (there was no chain, no
`prev` field, and no `verify`):

- link_hash is deterministic and changes if any covered field changes;
- a chained post stores `prev`; the first record anchors to GENESIS; each links to the last;
- verify on a clean chained log reports the chain intact, every record ok, and exits 0;
- verify detects deletion, reordering, insertion, and in-place text edits, and names the first
  broken line;
- an in-place text edit trips BOTH the HMAC (forged) and the chain (broken) — the two layers are
  independent;
- verify on an unchained log reports "no chain" and is still clean (content signatures only);
- --strict fails on unsigned/unverified records; plain verify does not;
- verify tolerates a corrupt line (reports it, marks the log tampered) rather than raising;
- the documented truncation limit: dropping the newest records leaves a valid prefix chain;
- the default (unchained) post writes NO `prev` field — the 0.2.0 wire format is unchanged.
"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.bus import MessageBus                                    # noqa: E402
from dan_oss_bridge.chain import GENESIS, link_hash                          # noqa: E402
from dan_oss_bridge.cli import main                                         # noqa: E402
from dan_oss_bridge.keyring import Keyring                                  # noqa: E402
from dan_oss_bridge.verify import verify_log                                # noqa: E402


class LinkHashTests(unittest.TestCase):
    def test_link_hash_is_deterministic_and_64_hex(self):
        h1 = link_hash(GENESIS, "c", "a", "hello", 1.5, "")
        h2 = link_hash(GENESIS, "c", "a", "hello", 1.5, "")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 64)
        bytes.fromhex(h1)  # valid hex

    def test_link_hash_changes_when_any_covered_field_changes(self):
        base = link_hash(GENESIS, "c", "a", "hello", 1.5, "")
        self.assertNotEqual(base, link_hash("x" * 64, "c", "a", "hello", 1.5, ""))  # prev
        self.assertNotEqual(base, link_hash(GENESIS, "c2", "a", "hello", 1.5, ""))  # channel
        self.assertNotEqual(base, link_hash(GENESIS, "c", "a2", "hello", 1.5, ""))  # agent
        self.assertNotEqual(base, link_hash(GENESIS, "c", "a", "HELLO", 1.5, ""))   # text
        self.assertNotEqual(base, link_hash(GENESIS, "c", "a", "hello", 2.5, ""))   # ts
        self.assertNotEqual(base, link_hash(GENESIS, "c", "a", "hello", 1.5, "ab")) # hmac

    def test_genesis_is_all_zero_and_distinct_from_any_real_link(self):
        self.assertEqual(GENESIS, "0" * 64)
        self.assertNotEqual(GENESIS, link_hash(GENESIS, "c", "a", "t", 1.0, ""))


class ChainedPostTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"
        self.bus = MessageBus(self.path, chain=True)  # chain on, no keyring (unsigned + chained)

    def tearDown(self):
        self._tmp.cleanup()

    def _records(self):
        return [json.loads(l) for l in self.path.read_text().splitlines() if l.strip()]

    def test_first_record_anchors_to_genesis(self):
        self.bus.post("c", "a", "first")
        recs = self._records()
        self.assertEqual(recs[0]["prev"], GENESIS)

    def test_each_record_links_to_the_previous(self):
        self.bus.post("c", "a", "one")
        self.bus.post("c", "a", "two")
        self.bus.post("c", "a", "three")
        recs = self._records()
        for i in range(1, len(recs)):
            p = recs[i - 1]
            expected = link_hash(p["prev"], p["channel"], p["agent"], p["text"], p["ts"],
                                 p.get("hmac", ""))
            self.assertEqual(recs[i]["prev"], expected, f"record {i} does not link to {i-1}")

    def test_returned_message_carries_prev(self):
        m = self.bus.post("c", "a", "x")
        self.assertEqual(m.prev, GENESIS)
        m2 = self.bus.post("c", "a", "y")
        self.assertTrue(m2.prev and m2.prev != GENESIS)


class UnchainedWireCompatTests(unittest.TestCase):
    """The default (chain off) must write the exact 0.2.0 wire format — no `prev` key."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_unchained_unsigned_post_has_no_prev_and_no_hmac(self):
        MessageBus(self.path).post("c", "anyone", "plain")  # no keyring, no chain
        rec = json.loads(self.path.read_text().splitlines()[0])
        self.assertNotIn("prev", rec)
        self.assertNotIn("hmac", rec)
        self.assertEqual(set(rec), {"channel", "agent", "text", "ts"})

    def test_signed_but_unchained_post_has_hmac_but_no_prev(self):
        kr = Keyring(Path(self._tmp.name) / "agents.json")
        kr.register("a")
        MessageBus(self.path, keyring=kr).post("c", "a", "signed")  # keyring on, chain off
        rec = json.loads(self.path.read_text().splitlines()[0])
        self.assertIn("hmac", rec)
        self.assertNotIn("prev", rec)


class VerifyCleanTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"
        self.kr = Keyring(Path(self._tmp.name) / "agents.json")
        self.kr.register("agent-a")
        self.bus = MessageBus(self.path, keyring=self.kr, chain=True)  # signed + chained

    def tearDown(self):
        self._tmp.cleanup()

    def test_clean_signed_chained_log_verifies(self):
        for t in ("one", "two", "three"):
            self.bus.post("standup", "agent-a", t)
        report = verify_log(self.path, self.kr)
        self.assertEqual(report.total, 3)
        self.assertEqual(report.ok, 3)
        self.assertEqual(report.forged, 0)
        self.assertTrue(report.chain_present)
        self.assertTrue(report.chain_intact)
        self.assertIsNone(report.first_break_line)
        self.assertFalse(report.tampered)
        self.assertTrue(report.clean())
        self.assertTrue(report.clean(strict=True))  # all signed & verified

    def test_empty_log_is_clean(self):
        self.path.write_text("", encoding="utf-8")
        report = verify_log(self.path, self.kr)
        self.assertEqual(report.total, 0)
        self.assertFalse(report.tampered)
        self.assertTrue(report.clean())

    def test_missing_log_cannot_be_assessed_as_clean(self):
        report = verify_log(Path(self._tmp.name) / "nope.jsonl", self.kr)
        self.assertEqual(report.total, 0)
        self.assertFalse(report.clean())
        self.assertTrue(report.missing)


class VerifyDetectsTamperingTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"
        self.kr = Keyring(Path(self._tmp.name) / "agents.json")
        self.kr.register("agent-a")
        self.bus = MessageBus(self.path, keyring=self.kr, chain=True)
        for t in ("one", "two", "three", "four"):
            self.bus.post("standup", "agent-a", t)

    def tearDown(self):
        self._tmp.cleanup()

    def _lines(self):
        return self.path.read_text(encoding="utf-8").splitlines()

    def _write(self, lines):
        self.path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_deleting_a_middle_record_breaks_the_chain(self):
        lines = self._lines()
        del lines[1]  # drop "two"
        self._write(lines)
        report = verify_log(self.path, self.kr)
        self.assertFalse(report.chain_intact)
        self.assertEqual(report.first_break_line, 2)  # the record now in slot 2 no longer links
        self.assertTrue(report.tampered)
        self.assertFalse(report.clean())

    def test_reordering_records_breaks_the_chain(self):
        lines = self._lines()
        lines[1], lines[2] = lines[2], lines[1]  # swap "two" and "three"
        self._write(lines)
        report = verify_log(self.path, self.kr)
        self.assertFalse(report.chain_intact)
        self.assertEqual(report.first_break_line, 2)
        self.assertTrue(report.tampered)

    def test_inserting_a_foreign_record_breaks_the_chain(self):
        lines = self._lines()
        forged = json.dumps({"channel": "standup", "agent": "agent-a", "text": "injected",
                             "ts": 9.9, "prev": GENESIS})
        lines.insert(2, forged)
        self._write(lines)
        report = verify_log(self.path, self.kr)
        self.assertFalse(report.chain_intact)
        self.assertEqual(report.first_break_line, 3)  # the injected line's prev is wrong
        self.assertTrue(report.tampered)

    def test_editing_signed_text_trips_both_hmac_and_chain(self):
        lines = self._lines()
        lines[1] = lines[1].replace("two", "TWO")  # edit the stored text of record 2
        self._write(lines)
        report = verify_log(self.path, self.kr)
        # HMAC layer: the edited record no longer verifies.
        self.assertGreaterEqual(report.forged, 1)
        edited = report.records[1]
        self.assertEqual(edited.auth, "forged")
        # Chain layer: the NEXT record's prev no longer matches the edited record's new link.
        self.assertFalse(report.chain_intact)
        self.assertEqual(report.first_break_line, 3)
        self.assertTrue(report.tampered)

    def test_corrupt_line_is_reported_not_raised(self):
        lines = self._lines()
        lines.insert(2, "this is not json")
        self._write(lines)
        report = verify_log(self.path, self.kr)  # must not raise
        self.assertEqual(report.corrupt, 1)
        self.assertTrue(report.tampered)
        self.assertFalse(report.clean())


class VerifyUnchainedAndStrictTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "bus.jsonl"
        self.kr = Keyring(Path(self._tmp.name) / "agents.json")

    def tearDown(self):
        self._tmp.cleanup()

    def test_unchained_signed_log_reports_no_chain_but_is_clean(self):
        self.kr.register("agent-a")
        bus = MessageBus(self.path, keyring=self.kr)  # signed, NOT chained
        bus.post("c", "agent-a", "x")
        bus.post("c", "agent-a", "y")
        report = verify_log(self.path, self.kr)
        self.assertFalse(report.chain_present)
        self.assertIsNone(report.chain_intact)
        self.assertEqual(report.ok, 2)
        self.assertFalse(report.tampered)
        self.assertTrue(report.clean())

    def test_unsigned_log_is_clean_by_default_but_fails_strict(self):
        MessageBus(self.path).post("c", "anyone", "unsigned")  # no keyring, no chain
        report = verify_log(self.path, self.kr)
        self.assertEqual(report.unsigned, 1)
        self.assertFalse(report.tampered)
        self.assertTrue(report.clean())              # unsigned alone is not tampering
        self.assertFalse(report.clean(strict=True))  # strict wants every message signed

    def test_keyless_verify_does_not_claim_forged(self):
        # A signed, chained log audited with no keyring: signatures can't be checked, but the chain
        # still verifies and nothing is falsely called "forged".
        self.kr.register("agent-a")
        MessageBus(self.path, keyring=self.kr, chain=True).post("c", "agent-a", "x")
        report = verify_log(self.path, keyring=None)
        self.assertFalse(report.keyring_available)
        self.assertEqual(report.forged, 0)
        self.assertTrue(report.chain_present)
        self.assertTrue(report.chain_intact)
        self.assertTrue(report.clean())


class TruncationLimitTests(unittest.TestCase):
    """Documented inherent limit: dropping the NEWEST records leaves a valid prefix chain — a
    single local file cannot prove its own tail wasn't truncated without an external head anchor."""

    def test_truncating_the_tail_leaves_a_valid_prefix(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / "bus.jsonl"
        kr = Keyring(Path(tmp.name) / "agents.json")
        kr.register("agent-a")
        bus = MessageBus(path, keyring=kr, chain=True)
        for t in ("one", "two", "three"):
            bus.post("c", "agent-a", t)
        lines = path.read_text().splitlines()
        path.write_text("\n".join(lines[:2]) + "\n", encoding="utf-8")  # drop the last record
        report = verify_log(path, kr)
        self.assertTrue(report.chain_intact)  # the remaining prefix is internally consistent
        self.assertEqual(report.total, 2)


class VerifyCliTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bus_path = str(Path(self._tmp.name) / "bus.jsonl")
        self.keyring_path = str(Path(self._tmp.name) / "agents.json")

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self, *args):
        buf_out, buf_err = io.StringIO(), io.StringIO()
        os.environ.pop("DAN_OSS_BRIDGE_NO_AUTH", None)
        os.environ.pop("DAN_OSS_BRIDGE_CHAIN", None)
        with redirect_stdout(buf_out), redirect_stderr(buf_err):
            code = main(["--bus", self.bus_path, "--keyring", self.keyring_path, *args])
        return code, buf_out.getvalue(), buf_err.getvalue()

    def test_chain_post_then_verify_is_clean_exit_zero(self):
        self._run("register", "agent-a")
        self._run("--chain", "post", "standup", "agent-a", "hello")
        self._run("--chain", "post", "standup", "agent-a", "again")
        code, out, _ = self._run("verify")
        self.assertEqual(code, 0)
        self.assertIn("chain intact", out)
        self.assertIn("VERDICT: clean", out)

    def test_verify_detects_tampering_exit_one(self):
        self._run("register", "agent-a")
        self._run("--chain", "post", "standup", "agent-a", "hello")
        self._run("--chain", "post", "standup", "agent-a", "again")
        # tamper: edit the first record's text on disk
        p = Path(self.bus_path)
        lines = p.read_text().splitlines()
        lines[0] = lines[0].replace("hello", "HELLO")
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        code, out, _ = self._run("verify")
        self.assertEqual(code, 1)
        self.assertIn("TAMPERING DETECTED", out)

    def test_verify_json_shape(self):
        self._run("register", "agent-a")
        self._run("--chain", "post", "standup", "agent-a", "hello")
        code, out, _ = self._run("verify", "--json")
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["total"], 1)
        self.assertTrue(data["chain_present"])
        self.assertTrue(data["chain_intact"])
        self.assertTrue(data["clean"])
        self.assertEqual(len(data["records"]), 1)

    def test_chain_via_env_var(self):
        self._run("register", "agent-a")
        os.environ["DAN_OSS_BRIDGE_CHAIN"] = "1"
        try:
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(io.StringIO()):
                main(["--bus", self.bus_path, "--keyring", self.keyring_path,
                      "post", "standup", "agent-a", "via-env"])
        finally:
            os.environ.pop("DAN_OSS_BRIDGE_CHAIN", None)
        rec = json.loads(Path(self.bus_path).read_text().splitlines()[0])
        self.assertIn("prev", rec)

    def test_verify_strict_fails_on_unsigned_via_cli(self):
        # Post with auth disabled -> unsigned line, then strict verify should exit 1.
        os.environ["DAN_OSS_BRIDGE_NO_AUTH"] = "1"
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                main(["--bus", self.bus_path, "--keyring", self.keyring_path,
                      "post", "c", "ghost", "unsigned"])
        finally:
            os.environ.pop("DAN_OSS_BRIDGE_NO_AUTH", None)
        code, out, _ = self._run("verify")
        self.assertEqual(code, 0)  # unsigned alone is clean
        code, out, _ = self._run("verify", "--strict")
        self.assertEqual(code, 1)  # strict rejects unsigned


if __name__ == "__main__":
    unittest.main()
