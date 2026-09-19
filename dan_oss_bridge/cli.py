"""dan_oss_bridge.cli — the real CLI: `dan-oss-bridge register|post|read|channels|verify`.

Per-agent identity is ON by default: an agent must be registered (own a local key) before it can
post, every post is signed, and reads flag any message that does not verify as UNVERIFIED. Set
`DAN_OSS_BRIDGE_NO_AUTH=1` to restore the original unauthenticated behaviour (the local-trust mode).

`--chain` (or `DAN_OSS_BRIDGE_CHAIN=1`) turns on whole-log tamper-evidence: each post is hash-chained
to the one before it, so `dan-oss-bridge verify` can prove no record was deleted, reordered, or
inserted. `verify` audits any log and exits non-zero if it finds tampering — usable straight in CI.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__
from .bus import MessageBus
from .keyring import Keyring, default_keyring_path
from .verify import _safe_terminal, format_report, report_to_dict, verify_log


def _default_bus_path() -> str:
    return os.environ.get("DAN_OSS_BRIDGE_BUS") or str(Path.home() / ".dan-oss-bridge" / "bus.jsonl")


def _auth_disabled() -> bool:
    """True when the operator has opted out of per-agent identity for this invocation."""
    return os.environ.get("DAN_OSS_BRIDGE_NO_AUTH") == "1"


def _chain_enabled(flag: bool) -> bool:
    """True when hash-chaining is on for this invocation: the `--chain` flag or DAN_OSS_BRIDGE_CHAIN=1."""
    return flag or os.environ.get("DAN_OSS_BRIDGE_CHAIN") == "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dan-oss-bridge", description="A unified agent communication bus.")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--bus", default=None, help="path to the real bus file (default: ~/.dan-oss-bridge/bus.jsonl)")
    parser.add_argument("--keyring", default=None,
                        help="path to the agent keyring (default: ~/.dan-oss-bridge/agents.json, "
                             "or $DAN_OSS_BRIDGE_KEYRING)")
    parser.add_argument("--chain", action="store_true",
                        help="hash-chain each post to the previous one for whole-log "
                             "tamper-evidence (or set DAN_OSS_BRIDGE_CHAIN=1); verify with `verify`")
    sub = parser.add_subparsers(dest="command", required=True)

    p_register = sub.add_parser("register", help="register an agent (create its signing key)")
    p_register.add_argument("agent")
    p_register.add_argument("--rotate", action="store_true",
                            help="replace an existing key with a fresh one")

    p_post = sub.add_parser("post", help="post a real message to a real channel")
    p_post.add_argument("channel")
    p_post.add_argument("agent")
    p_post.add_argument("text")

    p_read = sub.add_parser("read", help="read real messages")
    p_read.add_argument("channel", nargs="?", default=None)
    p_read.add_argument("--limit", type=int, default=50,
                        help="most-recent messages to return; <= 0 returns nothing (default: 50)")
    p_read.add_argument("--json", action="store_true", dest="as_json",
                        help="emit the messages as a JSON array (for scripts / CI)")

    p_channels = sub.add_parser("channels", help="list every real channel that has received a post")
    p_channels.add_argument("--json", action="store_true", dest="as_json",
                            help="emit the channel names as a JSON list (for scripts / CI)")

    p_verify = sub.add_parser("verify", help="audit the whole log for tamper-evidence "
                                             "(signatures + hash chain)")
    p_verify.add_argument("--json", action="store_true", dest="as_json",
                          help="emit the audit as JSON (for scripts / CI)")
    p_verify.add_argument("--strict", action="store_true",
                          help="also fail (non-zero exit) if any message is unsigned or unverified")

    args = parser.parse_args(argv)

    keyring_path = args.keyring or default_keyring_path()
    keyring = Keyring(keyring_path)
    # Identity is on unless explicitly disabled. When disabled, the bus is built with no keyring,
    # which restores the original unauthenticated post and unflagged read.
    bus_keyring = None if _auth_disabled() else keyring
    bus = MessageBus(args.bus or _default_bus_path(), keyring=bus_keyring,
                     chain=_chain_enabled(args.chain))

    try:
        if args.command == "register":
            created = keyring.register(args.agent, rotate=args.rotate)
            if created and args.rotate:
                print(f"rotated key for agent {args.agent!r}; stored in {keyring_path!r}")
            elif created:
                print(f"registered agent {args.agent!r}; key stored in {keyring_path!r}")
            else:
                print(f"agent {args.agent!r} is already registered; key stored in "
                      f"{keyring_path!r} (use --rotate to replace it)")
            return 0

        if args.command == "post":
            bus.post(args.channel, args.agent, args.text)
            print(f"posted to {args.channel!r}")
            return 0

        if args.command == "read":
            msgs = bus.read(args.channel, limit=args.limit)
            if args.as_json:
                # A JSON array of one object per message. verified is the read-time verdict
                # (true/false, or null when identity is off) — never a stored field.
                print(json.dumps([
                    {"channel": m.channel, "agent": m.agent, "text": m.text,
                     "ts": m.ts, "verified": m.verified}
                    for m in msgs
                ], indent=2))
                return 0
            if not msgs:
                print("no real messages yet" if args.channel is None
                      else f"no real messages yet on {args.channel!r}")
                return 0
            for m in msgs:
                # FINDING 18 fix: terminal-safe output — attacker-controlled channel/agent/text
                # must not emit raw control/ANSI sequences to the operator's terminal.
                # verified is None when identity is off (no keyring) -> print plainly, as before.
                if m.verified is False:
                    print(f"[{_safe_terminal(m.channel)}] {_safe_terminal(m.agent)} (UNVERIFIED): {_safe_terminal(m.text)}")
                else:
                    print(f"[{_safe_terminal(m.channel)}] {_safe_terminal(m.agent)}: {_safe_terminal(m.text)}")
            return 0

        if args.command == "channels":
            names = bus.channels()
            if args.as_json:
                print(json.dumps(names, indent=2))
                return 0
            if not names:
                print("no real channels yet")
                return 0
            for name in names:
                print(_safe_terminal(name))
            return 0

        if args.command == "verify":
            # Verify uses the keyring to check signatures even when NO_AUTH is set for posting —
            # auditing is a read-only integrity check and should see the keys if they exist. The
            # chain is checked with or without a keyring.
            report = verify_log(bus.path, keyring)
            if args.as_json:
                print(json.dumps(report_to_dict(report, strict=args.strict), indent=2))
            else:
                print(format_report(report, strict=args.strict))
            # Exit code is the CI contract: 0 = clean, 1 = not clean (tampering, or — with
            # --strict — unsigned/unverified records). Reserved 2 stays for bad input/usage.
            return 0 if report.clean(strict=args.strict) else 1
    except ValueError as e:
        # bad input (empty channel/agent, oversize text, unregistered agent) — a clear message,
        # not a traceback.
        print(f"error: {e}", file=sys.stderr)
        return 2
    except OSError as e:
        # bad bus path (e.g. --bus pointing at a directory -> IsADirectoryError), permission
        # errors, etc. — surface a friendly one-liner instead of a raw traceback.
        print(f"error: cannot use bus file {str(bus.path)!r}: {e}", file=sys.stderr)
        return 2

    return 1  # pragma: no cover


if __name__ == "__main__":
    sys.exit(main())
