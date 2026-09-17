# Contributing

Thanks for considering a contribution to `dan-oss-bridge`, a DAN Systems open-source project under
the [STRATO-DAN](https://github.com/STRATO-DAN) organization.

## Before you file an issue

- Search existing open and closed issues first — your question or bug may already be answered.
- If it's a bug, include: what you ran, what you expected, what actually happened, and your OS +
  Python version (`python3 --version`). A minimal repro (a few `dan-oss-bridge` commands, or a
  short script against `MessageBus` directly) is worth more than a long description.
- If it's a feature request, describe the real problem it solves, not just the feature itself —
  it's easier to evaluate "I need X because Y" than a solution proposed in isolation.
- Security issues do **not** go in a public issue — see `SECURITY.md`.

## Submitting a pull request

1. Fork the repo and create a branch off `main` with a short, descriptive name
   (`fix-channel-name-validation`, not `patch-1`).
2. Keep the change focused. A PR that fixes one bug or adds one small feature is easy to review
   and merge; a PR that also reformats unrelated files or adds unrelated cleanup is not.
3. Add or update tests under `tests/` for your change and confirm they pass locally
   (`python3 -m unittest discover -s tests -v`) before opening the PR.
4. Write a clear PR description: what changed, why, and how you verified it.
5. Be responsive to review feedback — a PR that goes quiet for a long time may be closed and can
   always be reopened once it's picked back up.

## Coding standards

This is a deliberately small, focused tool. Unless there's a strong, stated reason otherwise:

- **Zero runtime dependencies.** `pyproject.toml` declares `dependencies = []`, and it stays that
  way — Python's own standard library (`json`, `pathlib`, `argparse`, `dataclasses`) covers
  everything this tool needs. If you think a dependency is genuinely required, say why in the PR
  description; it'll get real consideration, but the bar is high, and "download, install, use"
  with nothing else to pull in is the whole point of this tool.
- **`python3 -m pip install dan-oss-bridge` must keep working with nothing else installed.**
  Verify with a clean virtualenv, not just your own dev environment, which may already have
  packages installed that mask a real new dependency.
- **Honest failure over fabricated success.** If a channel doesn't exist, or the local bus file is
  missing/corrupt, say so plainly (a clear error, a documented empty result) — never silently
  substitute a fake result that looks like the real thing.
- **Test what you change.** A change without a real, run test is not verified — a syntax check or
  a read-through is not a functional test.

## License

By contributing, you agree your contribution is licensed under the same license as this repo (MIT,
see `LICENSE`). The "DAN" name and logo are trademarked separately and are not covered by the MIT
grant — see `TRADEMARK.md`.
