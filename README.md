# DAN-OSS-BRIDGE

A real, standalone, zero-dependency multi-channel communication bus for AI agents.

```bash
pip install dan-oss-bridge

dan-oss-bridge post standup agent-a "Starting on the auth refactor"
dan-oss-bridge post standup agent-b "Reviewing agent-a's PR now"
dan-oss-bridge read standup
# [standup] agent-a: Starting on the auth refactor
# [standup] agent-b: Reviewing agent-a's PR now

dan-oss-bridge channels
# standup
```

## Python API

```python
from dan_oss_bridge import MessageBus

bus = MessageBus("~/.dan-oss-bridge/bus.jsonl")
bus.post("standup", "agent-a", "Starting on the auth refactor")
bus.read("standup")     # -> [Message(channel="standup", agent="agent-a", ...)]
bus.channels()          # -> ["standup"]
```

## Honest scope

v1 is a real, generic, multi-**channel** post/read bus — any number of named channels, one real
local append-only log. It does **not** ship real Slack/Discord/Telegram/Signal integration yet.
Each of those is its own separate, real undertaking (real OAuth, real webhooks, a real external
dependency this zero-dependency tool doesn't currently carry) — shipping a real generic bus now
and treating each external platform as its own later, separately-scoped integration was the
honest call, rather than half-building four platform bridges at once.

## A separate, standalone build

This is a genuinely separate reimplementation, sharing zero code with any internal system it may
have been inspired by. Checked directly before this README was written: `grep -rn` across this
package's own source for any accidental internal reference (internal naming, internal file paths,
internal architecture comments) — clean. No internal code, no internal data path, no internal
naming leaked into this public build.

## License

MIT.
