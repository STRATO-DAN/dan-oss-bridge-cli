# Changelog

All notable changes to `dan-oss-bridge` are documented here.
This project uses [semantic versioning](https://semver.org/).

## [0.6.0] — 2026-09-24

### Security

- **Per-project default bus/keyring (breaking default change).** On a shared, multi-project
  machine, every caller that used the plain defaults (`~/.dan-oss-bridge/bus.jsonl`,
  `~/.dan-oss-bridge/agents.json`) landed in the SAME file — any project's agents could read
  every other project's message content (HMACs prove authenticity, not confidentiality).
  `DAN_OSS_BRIDGE_BUS`/`DAN_OSS_BRIDGE_KEYRING` (and `--bus`/`--keyring`) already let an operator
  opt into isolation, but nothing opted in by default. The default is now namespaced per project
  (the nearest git repository root, or the resolved working directory if none) — automatic, no
  configuration required, and two different real directories never collide. An explicit
  `--bus`/`--keyring` flag or env var still always wins outright, unchanged.
- **One-time legacy archive.** The first invocation that would use a default path and finds the
  old global `bus.jsonl`/`agents.json` still there renames it aside
  (`*.pre-2026-09-24-project-isolation-archive`) rather than deleting it or silently merging it
  into a project's new namespaced file — a shared-bus log mixes messages from whichever projects
  used to default into it, and that mixed history can't be honestly un-mixed after the fact.
  Idempotent; never touches a file the caller pointed at explicitly.

## [0.5.1] — 2026-09-19

### Fixed

- **Sealed HMAC (Finding 01).** Chained+signed posts now bind the chain position into the
  MAC under a versioned canonical form: a record copied and re-pointed at a new tail fails
  verification instead of verifying twice. Dual sealed-then-legacy verify keeps every
  pre-seal signature verifying — no history bricked. Non-strict verify names unsigned
  records on the verdict line (local-trust only).

## [0.5.0] — 2026-09-19

### Security

- **Terminal-safe output.** `channel`/`agent`/`text`/`note` fields are attacker-controlled (any
  sender can write them) and were printed to the operator's terminal verbatim, risking raw
  ANSI/control-sequence injection. All output paths (`read` and `verify`) now escape non-printable
  characters.
- **File/directory permissions restricted to owner-only** (0700 dir / 0600 file) for the bus log.
- `verify_log()` now treats a **missing log file** as not-clean (was: trivially reported "clean"),
  a **non-finite `ts`** as corrupt instead of silently coercing to 0.0, and detects **duplicate
  signed records** (possible replay), reported separately from tampering.
- `verify` now always checks against the keyring when one exists, regardless of `NO_AUTH`
  (posting-time auth and read-time integrity checking are different concerns).

## [0.4.0]

Cross-cutting polish: the CLI now speaks JSON on every read path, documents a uniform exit-code
contract, and ships a `Makefile` of reproducible developer tasks. Purely additive — no runtime
dependencies, no behaviour change to any existing command, and the default (human-readable) output
of every command is unchanged.

Added:

- **`--json` on `read` and `channels`.** `read --json` prints a JSON array of
  `{channel, agent, text, ts, verified}` objects (an empty array when there are no messages);
  `channels --json` prints a JSON list of channel names. Human output stays the default; `--json` is
  opt-in. (`verify --json` already existed since 0.3.0.) The `verified` field is the read-time
  verdict — `true`/`false`, or `null` when identity is off.
- **Top-level `--version`.** Prints `dan-oss-bridge <version>` (sourced from
  `dan_oss_bridge.__version__`) and exits `0`; `--help` is provided by argparse as before.
- **`Makefile` with uniform targets + `make help`.** `make test` runs the full suite;
  `make attack` runs only the adversarial tests (tamper detection, forged/unsigned/unregistered
  identity, corrupt-line tolerance); `make demo` is a reproducible post → verify → tamper → verify
  walk-through proving the `0`/`1` exit codes; `make bench` measures tail-bounded read latency at
  1k / 10k / 100k messages. Stdlib only — no build tooling required.
- **`BENCHMARKS.md` + `tools/bench_read.py`.** Real measured numbers showing `read --limit 50`
  latency stays flat as the log grows 100×, plus how to reproduce them (`make bench`).

Documentation:

- **README:** a new "Scriptable & CI" section documenting the `--json` read paths and the exit-code
  contract (`0` ok / `1` verify-found-tampering / `2` usage or bad input), a "Try the attacks:
  `make attack`" pointer, and a link to `BENCHMARKS.md`. Flags table, project-contents table, and
  the tests section updated (now **69 tests**).

Tests:

- Added CLI coverage for `read --json` / `channels --json` (including empty results) and `--version`
  (64 → 69 tests, all passing).

## [0.3.0]

Whole-log tamper-evidence — a bus that can prove its own log wasn't altered. The per-message HMAC
(0.2.0) proves a signed message's *own content* wasn't edited; it does not catch a writer who
deletes, reorders, or inserts whole records. An opt-in hash chain closes that, and a new `verify`
command audits it. Fully backward-compatible: the default wire format is unchanged.

Added:

- **`--chain` (or `DAN_OSS_BRIDGE_CHAIN=1`) hash-chains each post.** Every chained record stores
  `prev`, the SHA-256 of the record before it (first record anchors to a genesis constant). The link
  binds the record's content, its own signature, and its link to the prior record, so deletion,
  reordering, insertion, or an in-place edit breaks the chain at the following record. New module
  `dan_oss_bridge/chain.py` (`link_hash`, `GENESIS`) — pure stdlib `hashlib`/`json`.
- **`dan-oss-bridge verify [--json] [--strict]`.** Walks the whole log (not a tail window) and
  reports, per record, content authenticity (`ok`/`forged`/`unsigned`/`corrupt`) and chain status
  (`linked`/`BROKEN`), plus a whole-log verdict and the first broken line. Exits `0` on a clean log
  and `1` on tampering, so it drops into CI; `--strict` also fails on any unsigned/unverified record;
  `--json` emits the audit as machine-readable JSON. New module `dan_oss_bridge/verify.py`
  (`verify_log`, `LogReport`), exported from the package.

Design notes (deliberate, documented):

- **Chaining is opt-in because it changes the concurrency contract.** A chained post takes a short
  exclusive `fcntl.flock` on a sibling `<bus>.lock` file so the read-tip-then-append is atomic and
  the chain can't fork under concurrent writers — trading the default's lock-free concurrent appends
  for the integrity link. The lock is advisory and auto-released by the OS if the writer dies; where
  `fcntl` is unavailable (non-POSIX), chained mode assumes a single writer.
- **The signature is unchanged.** The HMAC still covers `(channel, agent, text, ts)` exactly as in
  0.2.0 and does *not* fold in the chain link, so signatures written before chaining existed still
  verify. Content-authenticity (HMAC) and log-integrity (chain) are independent, composable layers.
- **One honest limit:** the chain can't detect a truncated *tail* (dropping the newest records
  leaves a valid prefix) — that needs an external head anchor, out of scope for a single local file.
  See `SECURITY.md`.

Preserved: the append-only shape, oldest-first ordering, tail-bounded reads, the `limit<=0` clamp,
fsync-on-post durability, the per-message text cap, per-agent identity, and the full corrupt-line
tolerance. The **default (unchained) post writes the exact 0.2.0 wire format, byte for byte** — no
`prev` field — so existing logs and readers are unaffected.

Zero runtime dependencies unchanged — the chain uses the standard library (`hashlib`, `json`) and
the lock uses `fcntl`. 25 new tests (`tests/test_chain.py`), 64 total.

## [0.2.0]

Per-agent identity — the `agent` sender is no longer just a free-text label. **Breaking**: posting
now requires the agent to be registered, and a new signature field is added to the wire format.

Added:

- **A local agent keyring** (`dan_oss_bridge/keyring.py`). `dan-oss-bridge register <agent>`
  generates a random per-agent key (`secrets.token_hex(32)`) and stores it in a JSON keyring at
  `~/.dan-oss-bridge/agents.json` (mode `0600`), overridable with `--keyring` or
  `DAN_OSS_BRIDGE_KEYRING`. `register` is idempotent; `--rotate` replaces an existing key. The key
  bytes are never printed — only the keyring location is.
- **Signed posts.** Every post is signed with an HMAC-SHA256 over the canonical
  `(channel, agent, text, ts)` tuple using the sending agent's key, stored as an `hmac` field on
  the JSONL record.
- **Verified reads.** `read` recomputes each message's HMAC against the sending agent's key and
  tags it: a verified message prints as before (`[channel] agent: text`); a message with a
  missing/invalid signature, or from an agent the reader has no key for (including older unsigned
  messages), prints flagged `[channel] agent (UNVERIFIED): text`. Unverified messages are **shown,
  not dropped** — deny-by-default on trust, not on delivery.

Changed (breaking):

- **Posting requires registration by default.** An unregistered agent gets a clear error telling
  it to `register` first, rather than posting a message no reader can authenticate.
- Opt out with `DAN_OSS_BRIDGE_NO_AUTH=1`, which restores the original unauthenticated post and
  unflagged read (the documented local-trust mode). The Python `MessageBus` mirrors this: construct
  it with a `Keyring` for identity, or without one for the original behaviour.

Preserved: the append-only shape, oldest-first ordering, tail-bounded reads, the `limit<=0` clamp,
fsync-on-post durability, the per-message text cap, and the full corrupt-line tolerance — a bad
line is still skipped, now even while signatures are being verified.

Honest scope: the keys live in a local `0600` file, so a same-uid process that can read the keyring
can still forge a signature for any agent. This authenticates *across agents that do not share a
key*; it is not a defense against a same-user attacker. See `SECURITY.md`.

Zero runtime dependencies unchanged — HMAC uses the standard library (`hmac`, `hashlib`,
`secrets`). 17 new tests (`tests/test_identity.py`), 39 total.

## [0.1.1]

Robustness and trust-model hardening. No API changes; the append-only, lossless, oldest-first
behaviour is unchanged, and all previous tests still pass. 10 new regression tests (22 total).

Fixed — read-path corruption tolerance (a single bad line could previously deny reads to every
agent):

- A valid-JSON but non-object line (`123`, `"x"`, `[...]`) is now skipped instead of raising
  `AttributeError` on `.get`.
- A non-numeric `ts` is now defaulted to `0.0` for that message instead of raising `ValueError`
  and crashing the read.
- Invalid UTF-8 bytes in the log are decoded with `errors="replace"` instead of raising
  `UnicodeDecodeError` before per-line handling — one bad byte can no longer deny `read()` **or**
  `channels()` to the whole bus.

Fixed — read/write mechanics:

- `read(limit=N)` now seeks the log tail from EOF instead of loading the entire file into memory,
  so a read is bounded by the requested window rather than O(total file size). `channels()`
  streams the log forward one line at a time instead of materialising every message.
- `read(limit=0)` (and any `limit <= 0`) now returns an empty list. It previously returned the
  **entire** log (`out[0:]`), and a negative limit silently dropped messages from the front.
  `limit` is a most-recent-window cap, never an offset.
- `post()` now flushes and best-effort `fsync`s the appended line so a returned post is durable.
- `post()` rejects oversized `text` (default cap 1 MiB of UTF-8, `MAX_TEXT_BYTES`) so one message
  can't append an unbounded line that blows up every reader. This is a per-message guard, not
  whole-file rotation — rotate the log externally for long-lived deployments.
- The CLI now prints a clear one-line error (exit code 2) instead of a raw traceback when the
  bus path is unusable (e.g. `--bus` pointing at a directory) or the input is rejected.

Documented — trust model (unchanged by design, now stated plainly in `README.md` and
`SECURITY.md`): identity is caller-asserted (no auth/signing/per-agent identity — anyone with
local write access can post as any agent), and the log has no message id, nonce, or
tamper-evidence. Use the bus only inside a trust boundary you already control. A per-agent
key/HMAC and a message-id + hash-chain are flagged as deliberate product decisions for a future
version, not shipped in v1.

## [0.1.0]

Initial release: a real, standalone, zero-dependency multi-channel communication bus for AI
agents. `MessageBus` (`dan_oss_bridge/bus.py`) is a local, append-only, JSON-lines log; the
`dan-oss-bridge` CLI (`dan_oss_bridge/cli.py`) wraps `post` / `read` / `channels`. `dependencies =
[]` in `pyproject.toml`, verified against the real `pip install` in a clean virtualenv — nothing
beyond Python's own standard library is pulled in.

v1 is a real, generic post/read bus over any number of named channels — it does not ship real
Slack/Discord/Telegram/Signal integration. Each of those is its own separate, real undertaking
(real OAuth, real webhooks, a real external dependency this zero-dependency tool doesn't currently
carry); shipping a real generic bus now and treating each external platform as its own later,
separately-scoped integration was the honest call over half-building four platform bridges at
once.

12 real tests (`tests/test_bus.py`, `tests/test_cli.py`): post/read round-trip, multi-channel
isolation, oldest-first ordering, `limit` capping, persistence across a fresh `MessageBus`
instance, empty-channel/empty-bus honesty, and a real CLI round-trip via subprocess.
