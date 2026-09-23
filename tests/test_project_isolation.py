"""Tests for dan_oss_bridge.project and the per-project default bus/keyring path (real fix for
the cross-project confidentiality gap found in Muse's 2026-09-24 review — see project.py's own
docstring): the OLD default (~/.dan-oss-bridge/bus.jsonl) put every project on a shared machine
into the same bus/keyring unless an operator remembered to set DAN_OSS_BRIDGE_BUS/_KEYRING or pass
--bus/--keyring. The fix makes the default itself per-project, with no configuration required.
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.cli import _archive_legacy_shared_bus_file, _default_bus_path  # noqa: E402
from dan_oss_bridge.keyring import default_keyring_path                            # noqa: E402
from dan_oss_bridge.project import project_namespace                               # noqa: E402


def _git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


class ProjectNamespaceTests(unittest.TestCase):
    def test_two_different_git_repos_get_different_namespaces(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "repo-a"
            b = Path(tmp) / "repo-b"
            a.mkdir()
            b.mkdir()
            _git_init(a)
            _git_init(b)
            self.assertNotEqual(project_namespace(a), project_namespace(b))

    def test_same_repo_root_gets_the_same_namespace_every_time(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            root.mkdir()
            _git_init(root)
            self.assertEqual(project_namespace(root), project_namespace(root))

    def test_a_subdirectory_of_a_repo_resolves_to_the_same_namespace_as_its_root(self):
        # A caller running from deep inside a repo (the common case) must land in the SAME
        # project bus as one running from the repo root -- otherwise every subdirectory would
        # fragment into its own isolated (and therefore useless) bus.
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "repo"
            sub = root / "a" / "b" / "c"
            sub.mkdir(parents=True)
            _git_init(root)
            self.assertEqual(project_namespace(root), project_namespace(sub))

    def test_two_different_non_git_directories_with_the_same_basename_do_not_collide(self):
        # The dirname alone is only a human-readable label -- the hash of the real resolved path
        # is what actually guarantees uniqueness. Confirm that directly: two directories both
        # named "backend" in different parents must not produce the same namespace.
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp) / "one" / "backend"
            b = Path(tmp) / "two" / "backend"
            a.mkdir(parents=True)
            b.mkdir(parents=True)
            self.assertNotEqual(project_namespace(a), project_namespace(b))

    def test_a_plain_non_git_directory_still_gets_a_stable_namespace(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "not-a-repo"
            d.mkdir()
            self.assertEqual(project_namespace(d), project_namespace(d))


class DefaultPathOverrideTests(unittest.TestCase):
    """An explicit override must always win outright -- the per-project namespace only applies
    when nothing else was specified, exactly like the old global default did."""

    def test_DAN_OSS_BRIDGE_BUS_env_var_still_wins_over_the_project_default(self, monkeypatch=None):
        import os

        old = os.environ.get("DAN_OSS_BRIDGE_BUS")
        os.environ["DAN_OSS_BRIDGE_BUS"] = "/tmp/explicit-bus.jsonl"
        try:
            self.assertEqual(_default_bus_path(), "/tmp/explicit-bus.jsonl")
        finally:
            if old is None:
                os.environ.pop("DAN_OSS_BRIDGE_BUS", None)
            else:
                os.environ["DAN_OSS_BRIDGE_BUS"] = old

    def test_DAN_OSS_BRIDGE_KEYRING_env_var_still_wins_over_the_project_default(self):
        import os

        old = os.environ.get("DAN_OSS_BRIDGE_KEYRING")
        os.environ["DAN_OSS_BRIDGE_KEYRING"] = "/tmp/explicit-keyring.json"
        try:
            self.assertEqual(default_keyring_path(), "/tmp/explicit-keyring.json")
        finally:
            if old is None:
                os.environ.pop("DAN_OSS_BRIDGE_KEYRING", None)
            else:
                os.environ["DAN_OSS_BRIDGE_KEYRING"] = old

    def test_default_bus_path_is_namespaced_under_the_dan_oss_bridge_home_dir(self):
        import os

        old = os.environ.pop("DAN_OSS_BRIDGE_BUS", None)
        try:
            path = _default_bus_path()
            self.assertIn(".dan-oss-bridge", path)
            self.assertTrue(path.endswith("bus.jsonl"))
            # Exactly one more path segment than the old flat default (the namespace directory).
            self.assertNotEqual(path, str(Path.home() / ".dan-oss-bridge" / "bus.jsonl"))
        finally:
            if old is not None:
                os.environ["DAN_OSS_BRIDGE_BUS"] = old


class LegacyArchiveTests(unittest.TestCase):
    """The one-time migration off the old flat shared file."""

    def test_archives_an_existing_legacy_file_exactly_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            import dan_oss_bridge.cli as cli_mod

            home_dir = Path(tmp)
            legacy_dir = home_dir / ".dan-oss-bridge"
            legacy_dir.mkdir()
            legacy = legacy_dir / "bus.jsonl"
            legacy.write_text('{"channel":"c","agent":"a","text":"shared-history","ts":1}\n')

            original_home = Path.home
            try:
                Path.home = staticmethod(lambda: home_dir)  # type: ignore[method-assign]
                cli_mod._archive_legacy_shared_bus_file("bus.jsonl")
                archived = legacy_dir / "bus.jsonl.pre-2026-09-24-project-isolation-archive"
                self.assertTrue(archived.exists())
                self.assertFalse(legacy.exists())
                self.assertIn("shared-history", archived.read_text())

                # A second call is a real no-op: nothing left to archive, and it must never
                # raise or clobber the already-archived file.
                cli_mod._archive_legacy_shared_bus_file("bus.jsonl")
                self.assertTrue(archived.exists())
            finally:
                Path.home = original_home  # type: ignore[method-assign]

    def test_never_touches_a_file_that_does_not_exist(self):
        with tempfile.TemporaryDirectory() as tmp:
            import dan_oss_bridge.cli as cli_mod

            home_dir = Path(tmp)
            original_home = Path.home
            try:
                Path.home = staticmethod(lambda: home_dir)  # type: ignore[method-assign]
                cli_mod._archive_legacy_shared_bus_file("bus.jsonl")  # must not raise
                self.assertFalse((home_dir / ".dan-oss-bridge").exists())
            finally:
                Path.home = original_home  # type: ignore[method-assign]


if __name__ == "__main__":
    unittest.main()
