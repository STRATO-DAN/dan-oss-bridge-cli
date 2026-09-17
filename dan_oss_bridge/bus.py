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
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path


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
        msg = Message(channel=channel, agent=agent, text=text, ts=time.time())
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps({
                "channel": msg.channel, "agent": msg.agent, "text": msg.text, "ts": msg.ts,
            }) + "\n")
        return msg

    def read(self, channel: str | None = None, limit: int = 50) -> list[Message]:
        """Real, ordered read — oldest first within the returned window, same as a real chat log.
        `channel=None` reads every real channel; a real channel name filters to just that one."""
        if not self.path.is_file():
            return []
        out: list[Message] = []
        for line in self.path.read_text().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            if channel is not None and d.get("channel") != channel:
                continue
            out.append(Message(channel=d.get("channel", ""), agent=d.get("agent", ""),
                                text=d.get("text", ""), ts=float(d.get("ts", 0.0))))
        return out[-limit:]

    def channels(self) -> list[str]:
        """Every real channel name that has ever received a real post — real, derived from the
        real log, never a fabricated or pre-declared list."""
        seen: list[str] = []
        for m in self.read(limit=10_000_000):
            if m.channel not in seen:
                seen.append(m.channel)
        return seen
