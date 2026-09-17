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

> 🔴 **No authentication, by design — stated plainly, not left for you to discover.** The `agent`
> sender is **caller-asserted**: anyone with local write access to the bus file can post as any
> agent name, and the log carries no message id, nonce, or tamper-evidence. Use it **only inside a
> trust boundary you already control** — see [Trust model](#trust-model). Per-agent auth is a
> deliberate product decision, not an oversight (see [`SECURITY.md`](SECURITY.md)).

A local coordination log for cooperating agents: any number of agents post to and read from any
number of named channels, all backed by one plain, append-only file. No server, no broker, no
network — just a file and three commands.

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
dan-oss-bridge post <channel> <agent> "<text>"   # append a message to a channel
dan-oss-bridge read  <channel> [--limit N]       # read a channel (default: 50 most recent)
dan-oss-bridge channels                          # list every channel that has a message
```

Messages persist to `~/.dan-oss-bridge/bus.jsonl` by default (override with `--bus` or
`DAN_OSS_BRIDGE_BUS`), so they survive across processes and restarts.

## Worked example

Real output from a live run — two agents post to a `standup` channel, then read it back:

```console
$ dan-oss-bridge post standup agent-a "Starting on the auth refactor"
posted to 'standup'
$ dan-oss-bridge post standup agent-b "Reviewing agent-a's PR now"
posted to 'standup'

$ dan-oss-bridge read standup
[standup] agent-a: Starting on the auth refactor
[standup] agent-b: Reviewing agent-a's PR now

$ dan-oss-bridge channels
standup

$ dan-oss-bridge read standup --limit 1
[standup] agent-b: Reviewing agent-a's PR now
```

Messages are returned oldest-first, and `--limit N` reads only the N most recent (the read seeks
the tail of the file, so it stays fast on a large log — it's bounded by `N`, not the whole file).

## Python API

```python
from dan_oss_bridge import MessageBus

bus = MessageBus("~/.dan-oss-bridge/bus.jsonl")

bus.post("standup", "agent-a", "Starting on the auth refactor")
bus.read("standup")            # -> [Message(channel="standup", agent="agent-a", text=..., ts=...)]
bus.read("standup", limit=1)   # -> only the most recent message
bus.channels()                 # -> ["standup"]
```

`Message` is a small dataclass — `channel`, `agent`, `text`, `ts` (a POSIX timestamp). `post`
raises `ValueError` on an empty channel/agent or a text larger than 1 MiB.

## Configuration

| Setting | Default | What it does |
|---|---|---|
| `--bus <path>` | `~/.dan-oss-bridge/bus.jsonl` | Which log file to use (CLI flag) |
| `DAN_OSS_BRIDGE_BUS` | *(unset)* | Same as `--bus`, via environment (the flag wins if both are set) |
| `--limit <N>` | `50` | On `read`: how many of the most-recent messages to return |

## What it never does

- Never opens a network socket or a server — it is a file and a CLI, nothing listens.
- Never lets one bad line deny reads to everyone — a corrupt record (invalid UTF-8, non-JSON, a
  valid-JSON non-object, or a bad timestamp) is skipped, not fatal.
- Never loads the whole log to answer `read --limit N` — it seeks backward from the end, so read
  cost is bounded by `N`, not the file size.
- Never crashes on a bad invocation — an unwritable or directory `--bus` path is a clear one-line
  error and exit code, not a traceback.
- Never authenticates — see the trust model; identity is caller-asserted by design.

## Trust model

The bus is a **plain, local, append-only log with no authentication.** Be explicit about what that
means before you deploy it:

- **Identity is caller-asserted.** The `agent` field is whatever the caller passes — no auth, no
  signing, no per-agent identity. A message that says it is from `agent-a` only means *someone who
  could write the file typed `agent-a`*.
- **No tamper-evidence.** No message id, nonce, or hash chain. Anyone who can write the file can
  replay, edit, or remove messages, and a reader cannot tell.
- **Use it only inside a trust boundary you already control** — a single machine, or a set of
  local processes that already trust each other. It is a coordination log for cooperating agents,
  **not** a security boundary between mutually-distrusting parties.

Corrupt or hostile *content* can't deny service (the read path tolerates bad lines), but that is
data-tolerance, **not** authentication — the points above still hold. Hardening such as a per-agent
key/HMAC or a message-id + hash-chain is a deliberate product decision, intentionally not in v1.
See [`SECURITY.md`](SECURITY.md).

## When to use this

- **Best fit**: coordinating several cooperating local agents/processes on one machine — a shared
  scratchpad they can post status to and read each other's, with zero infrastructure.
- **Best fit**: a dead-simple, dependency-free message log for a script or tool that just needs to
  leave and read notes on named channels.

**Honest flip side**: this is not a networked message broker and not a security boundary — no auth,
no delivery guarantees across machines, no Slack/Discord/Telegram integration (v1 is a generic
local bus; external platform bridges are each their own separately-scoped undertaking). If you need
authenticated senders or cross-machine transport, this isn't it.

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
| `dan_oss_bridge/cli.py` | The CLI entry point — `post` / `read` / `channels`. |
| `dan_oss_bridge/bus.py` | `MessageBus` + `Message` — the real append-only log, tail-bounded reads, corrupt-line-tolerant parsing. |
| `dan_oss_bridge/__init__.py` | Public exports (`MessageBus`, `Message`). |
| `tests/` | Real unit tests (`python -m unittest discover -s tests`). |

## FAQ

**Can two agents post at the same time?** Yes — writes are append-only single lines, so concurrent
posts from separate processes interleave cleanly without corrupting each other.

**Can I read across all channels at once?** `read` takes a channel; omit the channel argument to
read across all of them. `channels` lists every channel that has received a post.

**What happens to a huge log over time?** Reads stay fast (tail-bounded), but the file only grows —
there's no built-in rotation yet. Rotate or truncate it yourself if it gets large.

**Is the `agent` field trustworthy?** No — see [Trust model](#trust-model). It's caller-asserted.

## Tests

```bash
python -m unittest discover -s tests
```

Runs the unit suite on the standard-library `unittest` runner — no dependencies to install. As of
this release that's **22 tests, all passing**, covering the post/read/channels round-trip, channel
isolation and oldest-first ordering, the `--limit` tail read, and the full corrupt-input class
(invalid UTF-8, non-JSON, valid-JSON non-object, bad timestamp) proving one bad line can't deny
reads to the whole bus, plus oversized-text rejection and friendly CLI errors on a bad bus path.

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
