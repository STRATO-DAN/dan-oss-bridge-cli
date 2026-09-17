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

## Trust model — read before you deploy

The bus is a **plain, local, append-only log with no authentication.** Be explicit with yourself
about what that means:

- **Identity is caller-asserted.** The `agent` field is whatever the caller passes. There is no
  auth, no signing, and no per-agent identity — **anyone with local write access to the bus file
  can post as any agent name.** A message that says it is from `agent-a` only means *someone who
  could write the file typed `agent-a`*.
- **No tamper-evidence.** The log has no message id, nonce, or hash chain. Messages can be
  replayed, edited, or removed by anyone who can write the file, and a reader cannot tell.
- **Use it only inside a trust boundary you already control** — a single machine, or a set of
  local processes you already trust with each other. It is a coordination log for cooperating
  agents, **not** a security boundary between mutually-distrusting parties, and not a substitute
  for a networked bus with real authentication.

Corrupt or hostile *content* can no longer deny service: a single malformed line (bad UTF-8,
non-JSON, a valid-JSON non-object, or a bad timestamp) is skipped, not fatal, so one bad write
can't stop every agent from reading. That is data-tolerance, **not** authentication — the trust
model above still holds.

Hardening such as a per-agent key/HMAC (sender authenticity, parity with a hosted dashboard) or a
message-id + hash-chain (replay/tamper-evidence) is a deliberate *product decision*, not an
oversight, and is intentionally **not** built into v1. See `SECURITY.md`.

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
