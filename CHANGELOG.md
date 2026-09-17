# Changelog

All notable changes to `dan-oss-bridge` are documented here.
This project uses [semantic versioning](https://semver.org/).

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
