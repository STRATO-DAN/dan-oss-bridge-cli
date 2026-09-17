<div align="center">

# [DAN] BRIDGE

**A real, standalone, zero-dependency multi-channel message bus for agents — post, read, and list shared channels from a plain local log.**

[![python](https://img.shields.io/badge/python-%E2%89%A53.9-3776ab.svg)](#dependencies)
[![runtime deps](https://img.shields.io/badge/runtime%20deps-0-2e9e56.svg)](#dependencies)
[![docs](https://img.shields.io/badge/docs-README-blue.svg)](#use)
[![license](https://img.shields.io/badge/license-MIT-informational.svg)](LICENSE)

</div>

> **⚡ Zero runtime dependencies.** Pure Python standard library (≥ 3.9) — no packages to resolve,
> no build step. `python -m unittest` tests it. Full breakdown under [Dependencies](#dependencies).

> 🔴 **Per-agent identity, with an honest caveat.** Each agent registers a local secret key; every
> post is signed with an HMAC over its `(channel, agent, text, ts)`, and a read flags any message
> that doesn't verify as `UNVERIFIED`. This stops one agent from spoofing another's name. It is
> **not** a defense against a same-user attacker: the keys live in a local `0600` file, so any
> process running as the same user that can read that file can still forge a signature. See
> [Trust model](#trust-model) and [`SECURITY.md`](SECURITY.md).

A local coordination log for cooperating agents: any number of agents register a signing key, then
post to and read from any number of named channels, all backed by one plain, append-only file. No
server, no broker, no network — just a file, a keyring, and four commands.

## Install

Not on PyPI yet — install from source:

```bash
pip install git+https://github.com/STRATO-DAN/dan-oss-bridge-cli.git
```

or clone and install:

```bash
git clone https://github.com/STRATO-DAN/dan-oss-bridge-cli.git
cd dan-oss-bridge-cli
pip install .
```

Pure standard library, so there is no dependency tree to resolve. Once it's published,
`pip install dan-oss-bridge` will work directly.

## Use

```bash
dan-oss-bridge register <agent> [--rotate]       # create (or rotate) an agent's signing key
dan-oss-bridge post <channel> <agent> "<text>"   # append a signed message to a channel
dan-oss-bridge read  <channel> [--limit N]       # read a channel (default: 50 most recent)
dan-oss-bridge channels                          # list every channel that has a message
```

An agent must be registered before it can post — registration mints a random secret key so its
messages can be signed. Messages persist to `~/.dan-oss-bridge/bus.jsonl` by default (override with
`--bus` or `DAN_OSS_BRIDGE_BUS`), and keys to `~/.dan-oss-bridge/agents.json` (override with
`--keyring` or `DAN_OSS_BRIDGE_KEYRING`), so both survive across processes and restarts.

## Worked example

Real output from a live run — two agents register, post to a `standup` channel, then read it back:

```console
$ dan-oss-bridge register agent-a
registered agent 'agent-a'; key stored in '/home/you/.dan-oss-bridge/agents.json'
$ dan-oss-bridge register agent-b
registered agent 'agent-b'; key stored in '/home/you/.dan-oss-bridge/agents.json'

$ dan-oss-bridge post standup agent-a "Starting on the cache refactor"
posted to 'standup'
$ dan-oss-bridge post standup agent-b "Reviewing agent-a's change now"
posted to 'standup'

$ dan-oss-bridge read standup
[standup] agent-a: Starting on the cache refactor
[standup] agent-b: Reviewing agent-a's change now

$ dan-oss-bridge channels
standup

$ dan-oss-bridge read standup --limit 1
[standup] agent-b: Reviewing agent-a's change now
```

Both posts verify against each agent's key, so they read back plainly. A message that does not
verify — an unknown agent, a tampered record, or an older unsigned line — reads back flagged so a
reader can tell:

```console
$ dan-oss-bridge read standup
[standup] agent-a: Starting on the cache refactor
[standup] stranger (UNVERIFIED): I promise I am agent-a
```

Messages are returned oldest-first, and `--limit N` reads only the N most recent (the read seeks
the tail of the file, so it stays fast on a large log — it's bounded by `N`, not the whole file).

### Turning identity off (local-trust mode)

Set `DAN_OSS_BRIDGE_NO_AUTH=1` to restore the original unauthenticated behaviour — posts need no
registration and are unsigned, and reads print every message plainly without the `UNVERIFIED` flag.
Use it only where every writer of the bus file is already trusted.

```console
$ DAN_OSS_BRIDGE_NO_AUTH=1 dan-oss-bridge post standup anyone "no key needed here"
posted to 'standup'
```

## Python API

```python
from dan_oss_bridge import MessageBus, Keyring

# With a keyring: identity is on — posts are signed, reads are verified.
keyring = Keyring("~/.dan-oss-bridge/agents.json")
keyring.register("agent-a")                    # idempotent; register(..., rotate=True) replaces
bus = MessageBus("~/.dan-oss-bridge/bus.jsonl", keyring=keyring)

bus.post("standup", "agent-a", "Starting on the cache refactor")
msgs = bus.read("standup")     # -> [Message(..., hmac="…", verified=True)]
msgs[0].verified               # -> True (False = UNVERIFIED, None = not checked)

# Without a keyring: the original unauthenticated behaviour.
plain = MessageBus("~/.dan-oss-bridge/bus.jsonl")
plain.post("standup", "anyone", "no key needed")   # unsigned; read leaves verified = None
```

`Message` is a small dataclass — `channel`, `agent`, `text`, `ts` (a POSIX timestamp), plus `hmac`
(the stored signature, empty if unsigned) and `verified` (a read-time verdict: `True`, `False` for
UNVERIFIED, or `None` when read without a keyring). `post` raises `ValueError` on an empty
channel/agent or a text larger than 1 MiB, and `UnregisteredAgentError` (a `ValueError` subclass)
when the bus has a keyring but the agent has no key.

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `--bus <path>` | `~/.dan-oss-bridge/bus.jsonl` | Which log file to use (CLI flag) |
| `DAN_OSS_BRIDGE_BUS` | *(unset)* | Same as `--bus`, via environment (the flag wins if both are set) |
| `--keyring <path>` | `~/.dan-oss-bridge/agents.json` | Which agent keyring file to use (CLI flag) |
| `DAN_OSS_BRIDGE_KEYRING` | *(unset)* | Same as `--keyring`, via environment (the flag wins if both are set) |
| `DAN_OSS_BRIDGE_NO_AUTH` | *(unset)* | `1` disables identity: unsigned posts, unflagged reads, no registration required |
| `--rotate` | *(off)* | On `register`: replace an already-registered agent's key with a fresh one |
| `--limit <N>` | `50` | On `read`: how many of the most-recent messages to return |

## What it never does

- Never opens a network socket or a server — it is a file and a CLI, nothing listens.
- Never lets one bad line deny reads to everyone — a corrupt record (invalid UTF-8, non-JSON, a
  valid-JSON non-object, or a bad timestamp) is skipped, not fatal.
- Never loads the whole log to answer `read --limit N` — it seeks backward from the end, so read
  cost is bounded by `N`, not the file size.
- Never crashes on a bad invocation — an unwritable or directory `--bus` path is a clear one-line
  error and exit code, not a traceback.
- Never drops a message it can't verify — an unverifiable message is **flagged** `UNVERIFIED`, never
  silently discarded (deny-by-default on trust, not on delivery).
- Never prints an agent's secret key — `register` reports only the keyring location, and the key
  file is written `0600`.
- Never claims more than it delivers — identity authenticates *across agents that don't share a
  key*, not against a same-user attacker who can read the local key file (see the trust model).

## Trust model

The bus is a **local, append-only log with per-agent identity.** Be explicit about exactly what
that buys you — and what it does not — before you deploy it:

- **The `agent` field is authenticated across agents.** Each agent registers a local secret key,
  every post is signed with an HMAC over its `(channel, agent, text, ts)`, and a read verifies that
  signature against the sending agent's key. A message that reads back **verified** could only have
  been produced by something holding that agent's key — one agent can no longer post under another
  agent's name just by typing it.
- **Unverifiable messages are flagged, not trusted and not dropped.** A message with a missing or
  invalid signature, from an agent the reader has no key for, or an older unsigned line, reads back
  as `UNVERIFIED`. The reader still sees it; it just isn't trusted.
- **The honest caveat: this is not a defense against a same-user attacker.** The keys live in a
  local file (`0600`). Any process running as the same user that can read that file can sign as any
  agent whose key is in it. Identity here separates *agents that don't share a key* — it does not
  protect against an attacker who already has local read access to your keyring. Pair it with OS
  file permissions and process isolation for the boundary you actually need.
- **No cross-message tamper-evidence.** There is no message-id or hash chain, so a writer with file
  access can still drop or reorder whole lines; per-message signatures detect edits to a signed
  message's content, not deletion or replay of entire records.
- **`DAN_OSS_BRIDGE_NO_AUTH=1`** turns identity off entirely (unsigned posts, unflagged reads) for
  the original local-trust mode, where every writer of the file is already trusted.

Corrupt or hostile *content* still can't deny service — the read path tolerates bad lines even
while verifying signatures. See [`SECURITY.md`](SECURITY.md) for the full statement.

## When to use this

- **Best fit**: coordinating several cooperating local agents/processes on one machine — a shared
  scratchpad they can post status to and read each other's, with zero infrastructure.
- **Best fit**: a dead-simple, dependency-free message log for a script or tool that just needs to
  leave and read notes on named channels.

**Honest flip side**: this is not a networked message broker and not a full security boundary. The
per-agent signing authenticates senders *across agents that don't share a key*, but it is not a
defense against a same-user attacker who can read the local key file, and there are no
delivery guarantees across machines and no Slack/Discord/Telegram integration (v1 is a generic
local bus; external platform bridges are each their own separately-scoped undertaking). If you need
cross-machine transport or protection against a local attacker who can read your keyring, this
isn't it.

## Dependencies

| | |
|---|---|
| **Runtime dependencies** | **0** — Python standard library only (`json`, `os`, `time`, `pathlib`, …) |
| **Install to run** | the package itself; no dependency tree |
| **Install to test** | none — tests run on the standard-library `unittest` runner |
| **Python** | ≥ 3.9 |

Nothing is added to your environment beyond the package, and nothing phones home.

## Project contents

| Path | What it is |
|---|---|
| `dan_oss_bridge/cli.py` | The CLI entry point — `register` / `post` / `read` / `channels`. |
| `dan_oss_bridge/bus.py` | `MessageBus` + `Message` — the append-only log, tail-bounded reads, corrupt-line-tolerant parsing, sign-on-post / verify-on-read. |
| `dan_oss_bridge/keyring.py` | `Keyring` — the local `0600` per-agent key store, plus the HMAC sign/verify helpers. |
| `dan_oss_bridge/__init__.py` | Public exports (`MessageBus`, `Message`, `Keyring`, `UnregisteredAgentError`). |
| `tests/` | Real unit tests (`python -m unittest discover -s tests`). |

## FAQ

**Can two agents post at the same time?** Yes — writes are append-only single lines, so concurrent
posts from separate processes interleave cleanly without corrupting each other.

**Can I read across all channels at once?** `read` takes a channel; omit the channel argument to
read across all of them. `channels` lists every channel that has received a post.

**What happens to a huge log over time?** Reads stay fast (tail-bounded), but the file only grows —
there's no built-in rotation yet. Rotate or truncate it yourself if it gets large.

**Is the `agent` field trustworthy?** Across agents, yes — a **verified** message was signed with
that agent's key, so a different agent can't post under the name. But it is **not** trustworthy
against a same-user attacker who can read the local key file, and an `UNVERIFIED` message hasn't
been authenticated at all. See [Trust model](#trust-model).

## Tests

```bash
python -m unittest discover -s tests
```

Runs the unit suite on the standard-library `unittest` runner — no dependencies to install. As of
this release that's **39 tests, all passing**, covering the post/read/channels round-trip, channel
isolation and oldest-first ordering, the `--limit` tail read, and the full corrupt-input class
(invalid UTF-8, non-JSON, valid-JSON non-object, bad timestamp) proving one bad line can't deny
reads to the whole bus, plus oversized-text rejection and friendly CLI errors on a bad bus path —
and the identity layer: registration writes a `0600` keyring, a signed post verifies on read, a
forged/tampered/unsigned message reads `UNVERIFIED`, an unregistered agent can't post by default,
and `DAN_OSS_BRIDGE_NO_AUTH=1` restores the unauthenticated post.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to file an issue or submit a PR. Maintainers may use
AI tools to help review contributions — please don't include personal information in an issue, PR,
or commit beyond what's needed to describe the change.

## Releasing

See [RELEASING.md](RELEASING.md) — the same version-bump/tag/publish process applies to every
DAN-OSS tool, this one included.

## License

MIT (code) — see [`LICENSE`](LICENSE). The "DAN" name and logo are trademarked and not covered by
the MIT grant — see [`TRADEMARK.md`](TRADEMARK.md).
