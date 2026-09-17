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

> 🔗 **Prove your own log wasn't tampered with.** Opt into `--chain` and every post is hash-chained
> to the one before it, so `dan-oss-bridge verify` can prove no record was deleted, reordered, or
> inserted — and it exits non-zero the moment it isn't, so it drops straight into CI. See
> [Tamper-evidence](#tamper-evidence-the-hash-chain).

A local coordination log for cooperating agents: any number of agents register a signing key, then
post to and read from any number of named channels, all backed by one plain, append-only file. No
server, no broker, no network — just a file, a keyring, and five commands.

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
dan-oss-bridge [--chain] post ...                # ...and hash-chain it for tamper-evidence
dan-oss-bridge read  <channel> [--limit N] [--json]  # read a channel (default: 50 most recent)
dan-oss-bridge channels [--json]                 # list every channel that has a message
dan-oss-bridge verify [--json] [--strict]        # audit the whole log: signatures + hash chain
dan-oss-bridge --version                         # print the version (also: --help)
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

## Tamper-evidence (the hash chain)

The per-message signature proves a *signed message's own content* wasn't edited. It does **not**, on
its own, catch a writer who **deletes, reorders, or inserts whole records** — the surviving
signatures still verify. Opt into `--chain` and each post also stores `prev`, the SHA-256 of the
record before it, so the whole log becomes a linked chain. `dan-oss-bridge verify` then walks the
log end to end and proves the chain is unbroken — or names the exact line where it isn't.

Real output from a live run — two chained posts, then an attacker edits a delivered message on disk:

```console
$ dan-oss-bridge register agent-a
registered agent 'agent-a'; key stored in '/home/you/.dan-oss-bridge/agents.json'
$ dan-oss-bridge --chain post standup agent-a "deploying v2"
posted to 'standup'
$ dan-oss-bridge --chain post standup agent-a "tests green"
posted to 'standup'

$ dan-oss-bridge verify
  line 1: ok       chain=linked [standup] agent-a: deploying v2
  line 2: ok       chain=linked [standup] agent-a: tests green

2 record(s): 2 ok, 0 forged, 0 unsigned, 0 corrupt
chain intact
VERDICT: clean

# --- an attacker edits a delivered message on disk ---
$ dan-oss-bridge verify
  line 1: FORGED   chain=linked [standup] agent-a: deploying BACKDOOR  <- signature does not match the record content
  line 2: ok       chain=BROKEN [standup] agent-a: tests green  <- chain break: stored prev does not match the preceding record

2 record(s): 1 ok, 1 forged, 0 unsigned, 0 corrupt
CHAIN BROKEN at line 2
VERDICT: TAMPERING DETECTED
```

The edit trips **both** layers independently: the signature no longer matches (`FORGED`), and the
next record's `prev` no longer matches the edited record's new link (`chain=BROKEN`). `verify` exits
`0` on a clean log and `1` on any tampering, so it works straight in CI:

```bash
dan-oss-bridge verify --strict   # also fail if any message is unsigned/unverified
dan-oss-bridge verify --json     # the same audit as machine-readable JSON
```

Two deliberate boundaries, stated plainly:

- **Chaining is opt-in and takes a lock.** A chained post takes a short exclusive file lock so the
  read-tip-then-append stays atomic and the chain can't fork under concurrent writers — it trades
  the default's lock-free concurrent appends for the integrity link. Without `--chain`, posts write
  the exact original wire format and stay lock-free; `verify` still audits signatures.
- **The chain can't detect a dropped *tail*.** Truncating the newest records leaves a shorter,
  still-valid chain. Detecting a missing tail needs an external anchor (a recorded head hash), which
  is out of scope for a single local file — see [`SECURITY.md`](SECURITY.md).

## Scriptable & CI

Every read path speaks JSON, and every command speaks a stable exit code, so the bus drops into a
pipeline without screen-scraping:

```bash
dan-oss-bridge read standup --json   # JSON array: [{channel, agent, text, ts, verified}, ...]
dan-oss-bridge channels --json       # JSON list of channel names
dan-oss-bridge verify --json         # the whole audit as machine-readable JSON
```

Human-readable output stays the default; `--json` is purely additive. The `verified` field is the
read-time verdict — `true`/`false`, or `null` when identity is off.

**Exit-code contract** (uniform across commands, safe to branch on in CI):

| Code | Meaning |
|------|---------|
| `0`  | success — the command did what was asked (a clean `verify`, a completed `read`/`post`) |
| `1`  | `verify` found tampering (a forged signature, a broken chain, or a corrupt line); with `--strict`, also any unsigned/unverified record |
| `2`  | usage or bad input — unknown flags, a missing argument, an unregistered agent, an unusable bus path (a clear one-line error on stderr, never a traceback) |

**Try the attacks:** `make attack` runs only the adversarial suite — tamper detection, forged /
unregistered identity, and corrupt-line tolerance — and stays green because the library defends
against each. See also `make demo` (a full post → verify → tamper → verify walk-through) and
`make bench`, whose measured numbers live in [`BENCHMARKS.md`](BENCHMARKS.md): read latency stays
flat as the log grows 100×, because a read is bounded by its `--limit` window, not the file size.

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

# With chain=True: each post is hash-chained; verify_log audits the whole file.
from dan_oss_bridge import verify_log
chained = MessageBus("~/.dan-oss-bridge/bus.jsonl", keyring=keyring, chain=True)
chained.post("standup", "agent-a", "deploying v2")
report = verify_log("~/.dan-oss-bridge/bus.jsonl", keyring)
report.chain_intact      # -> True (False if a record was deleted/reordered/inserted/edited)
report.clean()           # -> True when no tampering; report.tampered is the inverse
report.first_break_line  # -> the 1-based line of the first broken link, or None
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
| `--chain` | *(off)* | On `post`: hash-chain the record to the previous one for whole-log tamper-evidence |
| `DAN_OSS_BRIDGE_CHAIN` | *(unset)* | Same as `--chain`, via environment (either one turns chaining on) |
| `--rotate` | *(off)* | On `register`: replace an already-registered agent's key with a fresh one |
| `--limit <N>` | `50` | On `read`: how many of the most-recent messages to return |
| `--json` | *(off)* | On `read`/`channels`/`verify`: emit machine-readable JSON instead of the human output |
| `--strict` | *(off)* | On `verify`: also fail (exit `1`) on any unsigned/unverified record |
| `--version` | — | Print the version and exit `0` (top-level; `--help` is also available) |

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
- **Cross-message tamper-evidence is available — opt in with `--chain`.** By default there is no
  hash chain, so a writer with file access can drop, reorder, or insert whole lines and the
  surviving per-message signatures still verify. Turn on `--chain` and each record links to the one
  before it, so `verify` proves the whole log is intact or names the first broken line — catching
  deletion, reordering, insertion, and in-place edits. Its one blind spot is a truncated *tail*
  (dropping the newest records leaves a valid prefix); detecting that needs an external head anchor.
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
| `dan_oss_bridge/cli.py` | The CLI entry point — `register` / `post` / `read` / `channels` / `verify`, `--json` on the read paths, `--version`. |
| `dan_oss_bridge/bus.py` | `MessageBus` + `Message` — the append-only log, tail-bounded reads, corrupt-line-tolerant parsing, sign-on-post / verify-on-read, and chained (`--chain`) append under a lock. |
| `dan_oss_bridge/keyring.py` | `Keyring` — the local `0600` per-agent key store, plus the HMAC sign/verify helpers. |
| `dan_oss_bridge/chain.py` | The hash-chain link function (`link_hash`, `GENESIS`) — pure, zero-dependency SHA-256 over a record's canonical fields. |
| `dan_oss_bridge/verify.py` | `verify_log` — walks the whole log and produces the tamper-evidence audit (`LogReport`). |
| `dan_oss_bridge/__init__.py` | Public exports (`MessageBus`, `Message`, `Keyring`, `UnregisteredAgentError`, `verify_log`, `link_hash`, …). |
| `tests/` | Real unit tests (`python -m unittest discover -s tests`). |
| `Makefile` | Uniform developer tasks — `make test` / `attack` / `demo` / `bench` / `help` (stdlib only). |
| `tools/bench_read.py` | The `make bench` script — measures tail-bounded read latency across log sizes. |
| `BENCHMARKS.md` | Measured `make bench` numbers and how to reproduce them. |

## FAQ

**Can two agents post at the same time?** Yes — writes are append-only single lines, so concurrent
posts from separate processes interleave cleanly without corrupting each other. With `--chain`,
concurrent posts serialize on a short file lock so the chain stays linear (the one deliberate
tradeoff chaining makes for tamper-evidence).

**Can I prove the log wasn't tampered with?** With `--chain`, yes: `dan-oss-bridge verify` proves no
record was deleted, reordered, inserted, or edited, or names the first broken line, and exits
non-zero on any tampering. See [Tamper-evidence](#tamper-evidence-the-hash-chain). Its one blind
spot is a truncated tail (see [Trust model](#trust-model)).

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
python -m unittest discover -s tests   # or: make test
```

Runs the unit suite on the standard-library `unittest` runner — no dependencies to install. As of
this release that's **69 tests, all passing**, covering the post/read/channels round-trip, channel
isolation and oldest-first ordering, the `--limit` tail read, and the full corrupt-input class
(invalid UTF-8, non-JSON, valid-JSON non-object, bad timestamp) proving one bad line can't deny
reads to the whole bus, plus oversized-text rejection and friendly CLI errors on a bad bus path;
the identity layer (registration writes a `0600` keyring, a signed post verifies on read, a
forged/tampered/unsigned message reads `UNVERIFIED`, an unregistered agent can't post by default,
`DAN_OSS_BRIDGE_NO_AUTH=1` restores the unauthenticated post); and the hash chain (a chained post
links to the previous record and anchors to genesis, `verify` reports a clean log and detects
deletion, reordering, insertion, and in-place edits at the exact line, `--strict`/`--json` behave,
and the documented tail-truncation limit holds); and the CLI surface itself (`read`/`channels`
`--json` emit parseable output, empty results stay empty JSON, and `--version` prints the version).

`make attack` re-runs just the adversarial slice of that suite (tamper detection, forged/unsigned/
unregistered identity, corrupt-line tolerance); `make demo` and `make bench` are described under
[Scriptable & CI](#scriptable--ci). Run `make help` to list every target.

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
