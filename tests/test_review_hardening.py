import json
import tempfile
import unittest
from pathlib import Path
from dan_oss_bridge.verify import verify_log, format_report


class ReviewHardeningTests(unittest.TestCase):
    def test_missing_is_not_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            report = verify_log(Path(directory) / "missing.jsonl")
            self.assertFalse(report.clean())
            self.assertIn("MISSING LOG", format_report(report))

    def test_duplicate_signed_record_is_flagged_even_without_chain(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bus.jsonl"
            line = json.dumps(dict(channel="c", agent="a", text="hi", ts=1, hmac="signature"))
            path.write_text(line + "\n" + line + "\n")
            report = verify_log(path)
            self.assertEqual(report.replayed, 1)
            self.assertFalse(report.clean())

    def test_terminal_controls_are_not_rendered(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bus.jsonl"
            path.write_text(json.dumps(dict(channel="c", agent="a", text="\x1b[2J\nspoof", ts=1)))
            rendered = format_report(verify_log(path))
            self.assertNotIn("\x1b", rendered)
            self.assertIn("\\u001b", rendered)

    def test_nonfinite_timestamp_is_corrupt(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bus.jsonl"
            path.write_text('{"ts": "NaN"}')
            self.assertEqual(verify_log(path).corrupt, 1)
