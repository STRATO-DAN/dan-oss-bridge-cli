"""dan_oss_bridge.keyring — per-agent identity: a local key store plus HMAC sign/verify.

Each agent that posts is registered with a random secret key, kept in a local JSON keyring file
(`~/.dan-oss-bridge/agents.json` by default, mode 0600). A posted message carries an
HMAC-SHA256 over its canonical tuple, computed with the sending agent's key. A reader
recomputes the HMAC with the same agent's key to decide whether the sender label is authentic.
Unchained posts sign the v1 tuple (channel, agent, text, ts); chained posts seal the chain
position too (v2: version, tuple, prev) so a copied record replayed at a new tail fails —
while every v1 signature ever written still verifies (see _canonical_bytes).

HONEST SCOPE — read this before relying on it: the keys live in a local file that any process
running as the same user can read. A same-uid attacker who can read the keyring can therefore forge
a signature for any agent. This authenticates *between agents that do not share a key* — it turns
the previously free-text `agent` label into something an unrelated agent (which does not hold that
key) cannot spoof — but it is **not** a defense against a same-user attacker who can read the key
file. Combine it with OS file permissions and process isolation for the boundary you actually need.
See SECURITY.md for the full statement.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
from pathlib import Path

# Keyring on-disk format version. Bumped only if the stored structure changes; readers key off it
# so an older keyring can be migrated rather than silently misread.
KEYRING_VERSION = 1

# A registered agent key is 32 random bytes, stored hex-encoded (64 chars). 256 bits is well past
# what HMAC-SHA256 needs and costs nothing here.
_KEY_BYTES = 32


def default_keyring_path() -> str:
    """Where the keyring lives unless overridden. `DAN_OSS_BRIDGE_KEYRING` wins; otherwise the
    per-user default alongside the default bus file."""
    return os.environ.get("DAN_OSS_BRIDGE_KEYRING") or str(
        Path.home() / ".dan-oss-bridge" / "agents.json"
    )


def _canonical_bytes(channel: str, agent: str, text: str, ts: float, prev: str = "") -> bytes:
    """One unambiguous byte string for a record. Two versions, domain-separated by a leading
    version element so they can never cross-verify:
      v1 (prev == ""): [channel, agent, text, ts] — the exact 0.2.0/0.3.0/0.4.0 bytes. Every
        signature ever written verifies here, forever; history is never invalidated.
      v2 (prev != ""): [2, channel, agent, text, ts, prev] — binds the chain position into the
        MAC, so a copied record replayed at a new tail fails verification (prev differs).
    A JSON array is used rather than a delimiter-joined string so a field that itself contains
    the delimiter cannot be rearranged to collide with a different tuple. `ts` is included
    exactly as the float that is stored, and JSON round-trips a Python float losslessly, so post
    and read canonicalise the same bytes."""
    if prev:
        return json.dumps(
            [2, channel, agent, text, ts, prev], separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8", "surrogatepass")
    return json.dumps(
        [channel, agent, text, ts], separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8", "surrogatepass")


def sign(key_hex: str, channel: str, agent: str, text: str, ts: float, prev: str = "") -> str:
    """HMAC-SHA256 of the canonical record under the agent's key, hex-encoded. `prev=""` signs
    exactly as before (v1, byte-identical); a non-empty `prev` seals the chain position (v2)."""
    return hmac.new(
        bytes.fromhex(key_hex), _canonical_bytes(channel, agent, text, ts, prev), hashlib.sha256
    ).hexdigest()


def verify(key_hex: str, channel: str, agent: str, text: str, ts: float, mac: str, prev: str = "") -> bool:
    """True only if `mac` is valid under `key_hex`. With a non-empty `prev` the sealed (v2)
    form is tried first and the legacy (v1) form second — so chained records written before
    sealing existed still verify, while a sealed record copied to a new tail fails both (its
    stored prev no longer matches, and its MAC is not a legacy MAC). A missing key or missing
    mac is a verification failure, never an exception. Uses a constant-time comparison."""
    if not key_hex or not mac:
        return False
    try:
        if prev and hmac.compare_digest(sign(key_hex, channel, agent, text, ts, prev), mac):
            return True
        expected = sign(key_hex, channel, agent, text, ts)
    except ValueError:
        # bytes.fromhex on a malformed stored key — treat as unverifiable, don't crash the read.
        return False
    return hmac.compare_digest(expected, mac)


class Keyring:
    """A local, file-backed map of agent name -> secret key. Loads lazily, writes with mode 0600.

    Missing file reads as an empty keyring. A corrupt keyring raises rather than being silently
    overwritten, so a bad file can never cause every registered key to be wiped by the next write.
    """

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def _load(self) -> dict[str, str]:
        if not self.path.is_file():
            return {}
        try:
            raw = self.path.read_text(encoding="utf-8")
            data = json.loads(raw)
        except (OSError, ValueError) as e:
            raise ValueError(f"keyring at {str(self.path)!r} is unreadable or corrupt: {e}") from e
        if not isinstance(data, dict):
            raise ValueError(f"keyring at {str(self.path)!r} is corrupt: not a JSON object")
        agents = data.get("agents", {})
        if not isinstance(agents, dict):
            raise ValueError(f"keyring at {str(self.path)!r} is corrupt: 'agents' is not an object")
        # Keep only well-formed string->string entries; ignore anything malformed rather than crash.
        return {k: v for k, v in agents.items() if isinstance(k, str) and isinstance(v, str)}

    def _save(self, agents: dict[str, str]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Best-effort tighten the containing directory; not required for correctness.
            os.chmod(self.path.parent, 0o700)
        except OSError:
            pass
        payload = json.dumps({"version": KEYRING_VERSION, "agents": agents}, indent=2) + "\n"
        # Create with 0600 from the start (umask may only tighten it further), then chmod to
        # guarantee 0600 even if the file already existed with looser permissions.
        fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
        try:
            os.chmod(self.path, 0o600)
        except OSError:
            pass

    def get(self, agent: str) -> str | None:
        """The agent's key (hex), or None if the agent is not registered."""
        return self._load().get(agent)

    def is_registered(self, agent: str) -> bool:
        return self.get(agent) is not None

    def register(self, agent: str, rotate: bool = False) -> bool:
        """Ensure `agent` has a key. Returns True if a new key was written (first registration or a
        rotation), False if the agent was already registered and `rotate` is False (a no-op).

        Idempotent: registering an already-registered agent without `rotate` leaves the existing
        key untouched. With `rotate=True` the existing key is replaced with a fresh one.
        """
        if not agent:
            raise ValueError("a real agent name is required to register")
        agents = self._load()
        if agent in agents and not rotate:
            return False
        agents[agent] = secrets.token_hex(_KEY_BYTES)
        self._save(agents)
        return True
