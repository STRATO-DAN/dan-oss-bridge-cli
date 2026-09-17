"""dan-oss-bridge — a unified interface for agent-to-agent communication channels.

Real, standalone, MIT-licensed. `MessageBus.post(channel, agent, text)` /
`MessageBus.read(channel=None, limit=50)` / `MessageBus.channels()`.

A fresh, standalone implementation sharing zero code with any other project — see this package's
own README for the explicit, checked confirmation.
"""
from .bus import Message, MessageBus

__all__ = ["Message", "MessageBus"]
__version__ = "0.1.1"
