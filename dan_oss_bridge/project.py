"""dan_oss_bridge.project — the per-project default namespace for the bus/keyring.

Real finding (Muse review sweep, 2026-09-24; independently re-verified): on a shared,
multi-project machine, every caller that uses the plain default paths
(`~/.dan-oss-bridge/bus.jsonl`, `~/.dan-oss-bridge/agents.json`) lands in the SAME file. HMACs on
a message prove who signed it, never who else is allowed to read it — so any project/agent using
the default lands in one shared, readable log with every other project on the box. `DAN_OSS_BRIDGE_BUS`
/ `DAN_OSS_BRIDGE_KEYRING` (and `--bus`/`--keyring`) already let an operator opt into isolation, but
nothing opts in by default, and a machine running many concurrent projects/agents cannot be kept
straight by everyone remembering to set an env var — the DEFAULT has to be the safe one.

The fix: the default is no longer one global path. It's namespaced by "which project this
invocation is running in" — the nearest git repository root if there is one (the real, already-
existing signal for "which project"), else the resolved current directory. This needs no per-
project configuration and no manually-maintained list of project names: two different real
directories never collide, and the same project always resolves to the same namespace across
every invocation/agent that runs from it.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def _git_root(start: Path) -> Path | None:
    """The nearest git repository root above `start`, or None if it isn't inside one (or `git`
    isn't available). Best-effort: any failure here just falls through to the cwd-based namespace
    below, never raises — this must never be the reason a bus/keyring path can't be computed."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    out = proc.stdout.strip()
    return Path(out) if out else None


def project_namespace(cwd: Path | None = None) -> str:
    """A short, filesystem-safe slug identifying the calling project: `<dirname>-<12 hex>`, where
    the hex suffix is a SHA-256 of the real, resolved project root path. The suffix (not the bare
    dirname) is what actually guarantees no collision — two different real directories that happen
    to share a name (e.g. two checkouts both named "backend") get different slugs; the dirname
    prefix is there only so the folder under `~/.dan-oss-bridge/` is human-identifiable at a
    glance, not for uniqueness.
    """
    start = (cwd or Path.cwd()).resolve()
    root = _git_root(start) or start
    root = root.resolve()
    digest = hashlib.sha256(str(root).encode()).hexdigest()[:12]
    name = root.name or "root"
    return f"{name}-{digest}"
