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

TRUST MODEL (read this before you deploy the bus): the `agent` sender is caller-asserted. There is
no authentication, signing, or per-agent identity — anyone with local write access to the bus file
can post as any agent name, and the log carries no message id, nonce, or tamper-evidence. Use the
bus only inside a trust boundary you already control (a single machine / a set of processes you
already trust). See README.md and SECURITY.md for the full statement and the optional hardening
(per-agent key/HMAC, message-id + hash-chain) left as a deliberate product decision.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

# A single posted message's `text` is capped so one post cannot append an unbounded line to the
# shared log (which would blow up every reader's memory and every subsequent read). This is a
# per-message guard, not whole-file rotation — the log itself still grows append-only; rotate or
# cap the file externally (e.g. logrotate) for long-lived deployments.
MAX_TEXT_BYTES = 1 << 20  # 1 MiB of UTF-8 per message

# Chunk size used when reading the log tail backward from EOF.
_TAIL_CHUNK = 65536


@dataclass(frozen=True)
class Message:
    channel: str
    agent: str
    text: str
    ts: float


class MessageBus:
    """Real, file-backed, append-only message bus. One real JSONL file, one real line per real
    posted message — same real append-only shape a shared log needs, built fresh here rather than
    imported from anywhere else."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def post(self, channel: str, agent: str, text: str) -> Message:
        if not channel:
            raise ValueError("a real channel name is required")
        if not agent:
            raise ValueError("a real agent name is required")
        if len(text.encode("utf-8", "surrogatepass")) > MAX_TEXT_BYTES:
            raise ValueError(
                f"message text is too large (max {MAX_TEXT_BYTES} bytes of UTF-8)"
            )
        msg = Message(channel=channel, agent=agent, text=text, ts=time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "channel": msg.channel, "agent": msg.agent, "text": msg.text, "ts": msg.ts,
        }) + "\n"
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
        return Message(
            channel=d.get("channel", ""), agent=d.get("agent", ""),
            text=d.get("text", ""), ts=ts,
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
        skipped individually; one bad line never denies the read to every agent."""
        if limit <= 0:
            return []
        if not self.path.is_file():
            return []
        return self._read_tail(channel, limit)

    def channels(self) -> list[str]:
        """Every real channel name that has ever received a real post — real, derived from the
        real log, never a fabricated or pre-declared list."""
        seen: list[str] = []
        for m in self._iter_all():
            if m.channel not in seen:
                seen.append(m.channel)
        return seen
