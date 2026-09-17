# Releasing

The real release process for `dan-oss-bridge`. Unlike its Node.js siblings under
[STRATO-DAN](https://github.com/STRATO-DAN) (`dan-oss-commit`, `dan-oss-mock`, `dan-oss-array`,
`dan-oss-recall-dashboard`, `dan-oss-bridge-dashboard`, which publish to npm), this is a Python
package and publishes to **PyPI**. The version-bump discipline and stop-at-PR convention are the
same; the tooling underneath is not.

## 1. Decide the version bump

Semantic versioning, same as every DAN-OSS tool:

- **patch** (`0.1.0` → `0.1.1`) — a bug fix, no behavior change a user would notice as new.
- **minor** (`0.1.0` → `0.2.0`) — a real new feature, backward compatible.
- **major** (`0.1.0` → `1.0.0`) — a breaking change (a CLI flag removed/renamed, a default
  behavior change, a Python version floor raised above what `requires-python` currently states).

## 2. Bump the version

Hand-edit the single `version = "X.Y.Z"` line in `pyproject.toml` — there is no `npm version`
equivalent wired up here yet (a `bump-my-version`/`hatch version` step is a reasonable future
addition, not done today). Commit that change on its own.

## 3. Tag and push

```bash
git tag -a vX.Y.Z -m "vX.Y.Z — <one-line summary>"
git push origin main --follow-tags
```

## 4. Build and publish to PyPI

```bash
python3 -m pip install --upgrade build twine   # build tooling only — never a runtime dependency
python3 -m build                               # produces dist/dan_oss_bridge-X.Y.Z-py3-none-any.whl + .tar.gz
python3 -m twine check dist/*                  # sanity-checks the built metadata before it ships
python3 -m twine upload dist/*
```

Before uploading, actually look at what `python3 -m build` produced — confirm the wheel contains
only `dan_oss_bridge/` and its real `.py` files, nothing else, the same discipline the npm
siblings apply via `npm pack --dry-run`.

Publishing requires PyPI auth for the `DAN Systems` PyPI account/project — use a scoped API token
(`~/.pypirc` or the `TWINE_PASSWORD` env var for that one upload), never a long-lived token
committed anywhere in a repo or workflow file.

## 5. Create the GitHub release

Create a release on GitHub for the new tag, with real release notes: what changed, any migration
notes for a breaking change, and a thank-you to any external contributor whose PR is included.

## What this process deliberately doesn't include yet

There is no CI-driven automated release pipeline for this tool yet — every step above is a real,
manual command a maintainer runs locally. That's an honest current limitation, not a design
decision to keep it manual forever.
