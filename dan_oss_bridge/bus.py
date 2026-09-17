"""dan_oss_bridge.bus — the real, standalone message bus behind dan-oss-bridge.

A fresh, from-scratch implementation, written to stand on its own — no code shared with, and no
dependency on, any other project.

HONEST SCOPE: v1 ships a real, generic, multi-CHANNEL post/read bus — any number of agents can
post to and read from any number of real, named channels backed by one real local log. It does
**not** ship Slack/Discord/Telegram/Signal integration. Each of those is its own real, separate
undertaking (real OAuth, real webhooks, a real external HTTP dependency this zero-dependency tool
does not currently carry) — shipping a real generic bus now and treating each external platform as
its own later, separately-scoped integration is the honest call, rather than half-building four
platform bridges at once.

TRUST MODEL (read this before you deploy the bus): the `agent` sender carries a per-agent identity.
When the bus is given a `Keyring`, each post is signed with an HMAC-SHA256 over its canonical
(channel, agent, text, ts) tuple using the sending agent's registered key, and a read verifies that
signature against the same agent's key — a message from an agent that does not hold the key (or an
old unsigned message) reads back flagged UNVERIFIED rather than being trusted or dropped. The keys
live in a local 0600 file, so this authenticates *between agents that do not share a key*; it is not
a defense against a same-user attacker who can read that file. A bus constructed without a keyring
keeps the original unauthenticated behaviour (the documented local-trust mode). See README.md and
SECURITY.md for the full statement.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, replace
from pathlib import Path

from .keyring import Keyring, sign as _sign, verify as _verify

# A single posted message's `text` is capped so one post cannot append an unbounded line to the
# shared log (which would blow up every reader's memory and every subsequent read). This is a
# per-message guard, not whole-file rotation — the log itself still grows append-only; rotate or
# cap the file externally (e.g. logrotate) for long-lived deployments.
MAX_TEXT_BYTES = 1 << 20  # 1 MiB of UTF-8 per message

# Chunk size used when reading the log tail backward from EOF.
_TAIL_CHUNK = 65536


class UnregisteredAgentError(ValueError):
    """Raised by `post` when the bus has a keyring but the sending agent has no key. A subclass of
    `ValueError` so callers already handling bad input catch it too; the message says how to fix it
    (register the agent). Bypass registration entirely with the documented no-auth mode."""


@dataclass(frozen=True)
class Message:
    channel: str
    agent: str
    text: str
    ts: float
    # HMAC-SHA256 (hex) over the canonical tuple, present when the message was signed at post time.
    # Empty for messages posted without a keyring (the local-trust mode) and for pre-identity logs.
    hmac: str = ""
    # Read-time verdict, never stored: True = signature verified, False = missing/invalid signature
    # or unknown agent (UNVERIFIED), None = not checked (read without a keyring).
    verified: "bool | None" = None


class MessageBus:
    """Real, file-backed, append-only message bus. One real JSONL file, one real line per real
    posted message — same real append-only shape a shared log needs, built fresh here rather than
    imported from anywhere else.

    Pass a `Keyring` to turn on per-agent identity: posts are signed and reads are verified. Without
    one the bus behaves exactly as before — unsigned posts, unverified reads (the local-trust mode).
    """

    def __init__(self, path: str | Path, keyring: Keyring | None = None):
        self.path = Path(path)
        self.keyring = keyring

    def post(self, channel: str, agent: str, text: str) -> Message:
        if not channel:
            raise ValueError("a real channel name is required")
        if not agent:
            raise ValueError("a real agent name is required")
        if len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
            raise ValueError(
                f"message text is too large (max {MAX_TEXT_BYTES} bytes of UTF-8)"
            )
        ts = time.time()
        record = {"channel": channel, "agent": agent, "text": text, "ts": ts}
        mac = ""
        if self.keyring is not None:
            # Identity is on: the agent must be registered, and the post is signed with its key.
            # Deny-by-default on TRUST — an unregistered agent cannot mint a trusted message.
            key = self.keyring.get(agent)
            if key is None:
                raise UnregisteredAgentError(
                    f"agent {agent!r} is not registered — run: dan-oss-bridge register {agent}"
                )
            mac = _sign(key, channel, agent, text, ts)
            record["hmac"] = mac
        msg = Message(channel=channel, agent=agent, text=text, ts=ts, hmac=mac)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(record) + "\n"
        # Append-only, one line per message (unchanged shape). flush + fsync make a returned
        # post best-effort durable on disk; fsync is best-effort because some filesystems /
        # platforms don't support it, and there is intentionally no atomic rename — a concurrent
        # reader that catches a half-written final line simply skips it (see read()).
        with self.path.open("a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # best-effort; not all targets support fsync
        return msg

    @staticmethod
    def _parse_line(raw: bytes | str) -> Message | None:
        """Parse one raw log line into a Message, or return None if the line is not a usable
        message. Tolerant by design: a single corrupt line must never deny reads to every agent.
        Guards against every confirmed corruption class — invalid UTF-8 bytes, non-JSON,
        valid-JSON-but-non-dict (e.g. ``123`` / ``"x"`` / ``[...]``), and a non-numeric ``ts``."""
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8", "replace")
        line = raw.strip()
        if not line:
            return None
        try:
            d = json.loads(line)
        except (ValueError, json.JSONDecodeError):
            return None
        if not isinstance(d, dict):
            # A valid-JSON scalar/array line (123, "x", [...]) has no .get — skip it.
            return None
        try:
            ts = float(d.get("ts", 0.0))
        except (TypeError, ValueError):
            ts = 0.0  # keep the message; a bad timestamp shouldn't drop or crash the read
        mac = d.get("hmac", "")
        if not isinstance(mac, str):
            mac = ""  # a non-string hmac (forged/corrupt) is treated as no signature
        return Message(
            channel=d.get("channel", ""), agent=d.get("agent", ""),
            text=d.get("text", ""), ts=ts, hmac=mac,
        )

    def _read_tail(self, channel: str | None, limit: int) -> list[Message]:
        """Return up to ``limit`` most-recent matching messages, oldest-first, by seeking backward
        from EOF a chunk at a time. We never load more of the log than the requested window needs,
        so read(limit=N) is bounded by N (plus one tail chunk) rather than O(total file size)."""
        collected: list[Message] = []  # newest-first while we walk backward
        buf = b""
        with self.path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            pos = f.tell()
            while pos > 0 and len(collected) < limit:
                read_size = min(_TAIL_CHUNK, pos)
                pos -= read_size
                f.seek(pos)
                buf = f.read(read_size) + buf
                parts = buf.split(b"\n")
                if pos > 0:
                    # The first segment may be a line cut off by the chunk boundary — carry it
                    # back into buf and complete it on the next (earlier) chunk.
                    buf = parts.pop(0)
                else:
                    buf = b""
                for raw in reversed(parts):
                    msg = self._parse_line(raw)
                    if msg is None:
                        continue
                    if channel is not None and msg.channel != channel:
                        continue
                    collected.append(msg)
                    if len(collected) >= limit:
                        break
        collected.reverse()  # oldest-first within the returned window
        return collected

    def _iter_all(self):
        """Stream every usable message forward, one line at a time — bounded memory even for a
        large log. Used by channels(); also decodes with errors='replace' so a single bad UTF-8
        byte can't deny the whole scan."""
        if not self.path.is_file():
            return
        with self.path.open("r", encoding="utf-8", errors="replace") as f:
            for raw in f:
                msg = self._parse_line(raw)
                if msg is not None:
                    yield msg

    def read(self, channel: str | None = None, limit: int = 50) -> list[Message]:
        """Real, ordered read — oldest first within the returned window, same as a real chat log.
        `channel=None` reads every real channel; a real channel name filters to just that one.

        `limit` is the size of the most-recent window returned. `limit <= 0` returns nothing (an
        empty list) — it is a cap, not an offset, so a zero or negative cap means "no messages"
        rather than "all messages". Corrupt lines (bad UTF-8, non-JSON, non-dict, bad ts) are
        skipped individually; one bad line never denies the read to every agent.

        When the bus has a keyring, each returned message is tagged `verified` (True/False) by
        checking its HMAC against the sending agent's key — an unsigned message, a bad signature,
        or an unknown agent reads back `verified=False` (UNVERIFIED), never dropped. Without a
        keyring, `verified` is left None (not checked)."""
        if limit <= 0:
            return []
        if not self.path.is_file():
            return []
        msgs = self._read_tail(channel, limit)
        if self.keyring is not None:
            msgs = [replace(m, verified=self._verify(m)) for m in msgs]
        return msgs

    def _verify(self, m: Message) -> bool:
        """True only if the message carries a valid signature for its agent's current key. A
        missing signature, a bad one, or an unknown agent is UNVERIFIED (False), never an error."""
        if self.keyring is None:
            return False
        key = self.keyring.get(m.agent)
        if key is None:
            return False
        return _verify(key, m.channel, m.agent, m.text, m.ts, m.hmac)

    def channels(self) -> list[str]:
        """Every real channel name that has ever received a real post — real, derived from the
        real log, never a fabricated or pre-declared list."""
        seen: list[str] = []
        for m in self._iter_all():
            if m.channel not in seen:
                seen.append(m.channel)
        return seen
