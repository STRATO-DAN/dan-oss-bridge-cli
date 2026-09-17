# Changelog

All notable changes to `dan-oss-bridge` are documented here.
This project uses [semantic versioning](https://semver.org/).

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
