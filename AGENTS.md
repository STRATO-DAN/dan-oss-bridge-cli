# AGENTS.md

Context for AI coding assistants (Claude, Copilot, Cursor, etc.) working in this repository.

## What this repo is

A small, focused, zero-runtime-dependency Python developer tool: a standalone `pip`-installable
package with a `dan-oss-bridge` CLI entry (`dan_oss_bridge/cli.py`) and a small library
(`dan_oss_bridge/bus.py`). No build step beyond standard `setuptools`, no framework, no shared
codebase with any other DAN-OSS tool (they're separate Node.js packages).

## House rules

- **Zero runtime dependencies.** `pyproject.toml` declares `dependencies = []` — Python's own
  standard library (`json`, `pathlib`, `argparse`, `dataclasses`, `time`) covers everything this
  tool needs. Reach for a dependency only when there's a real, specific reason the stdlib can't do
  it — and say what that reason is. Verify with a clean virtualenv install, not just your own dev
  environment, before claiming the tool still has none.
- **Honest failure over fabricated success.** A missing channel, a missing/corrupt local bus file,
  or a bad argument gets a clear error or a documented empty result — never a fake result that
  looks like the real thing.
- **Never leak internal identifiers into a public repo.** This is the one rule with two real
  incidents behind it across DAN Systems' other public repos, not a hypothetical:
  - An early pass across the org's public tools found internal Linear ticket IDs (`STR-xxx`),
    internal PR numbers, internal codenames, the internal monorepo name, and internal team/lane
    labels baked into shipped source comments and git commit messages — all fixed, but only after
    the fact, via a pre-commit hook scanning staged file content.
  - That fix had its own real gap: the hook only ever scanned staged *file* content, never the
    commit *message* text. An internal ticket ID and an AI-attribution line both slipped into a
    commit message anyway, on a commit whose diff was completely clean — caught only because the
    author happened to reread the message after committing, amended before it was ever pushed,
    then closed the gap for real with a second hook (`commit-msg`) that scans the message itself.
  - Before writing a comment OR a commit message in this repo: never reference an internal ticket
    ID, internal PR number, internal codename, an internal monorepo/repo name, or an internal
    team/lane label. Never reference internal infrastructure (IPs, hostnames, credential names,
    internal service URLs). If a design decision genuinely needs explaining, explain the
    *reasoning* in a way a stranger with zero internal context could follow — not a pointer to an
    internal ticket they can't see.
  - **Never add an AI-attribution line to a commit or PR in this repo** (`Co-Authored-By: Claude`,
    "Generated with Claude Code", or similar) — this is a real, standing, deliberately enforced
    rule for this org, not an oversight if it's missing.
- **Test what you change.** If a change is claimed to work, it should have actually been run
  (`python3 -m unittest discover -s tests -v`) — a syntax check is not a functional test.

## AI-assisted review

Human maintainers may use AI tools to help review contributions to this repo. Please don't include
personal information in your issue, PR, or commit content beyond what's needed to describe the
change.
