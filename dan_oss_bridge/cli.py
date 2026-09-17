"""dan_oss_bridge.cli — the real CLI: `dan-oss-bridge register|post|read|channels`.

Per-agent identity is ON by default: an agent must be registered (own a local key) before it can
post, every post is signed, and reads flag any message that does not verify as UNVERIFIED. Set
`DAN_OSS_BRIDGE_NO_AUTH=1` to restore the original unauthenticated behaviour (the local-trust mode).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .bus import MessageBus
from .keyring import Keyring, default_keyring_path


def _default_bus_path() -> str:
    return os.environ.get("DAN_OSS_BRIDGE_BUS") or str(Path.home() / ".dan-oss-bridge" / "bus.jsonl")


def _auth_disabled() -> bool:
    """True when the operator has opted out of per-agent identity for this invocation."""
    return os.environ.get("DAN_OSS_BRIDGE_NO_AUTH") == "1"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dan-oss-bridge", description="A unified agent communication bus.")
    parser.add_argument("--bus", default=None, help="path to the real bus file (default: ~/.dan-oss-bridge/bus.jsonl)")
    parser.add_argument("--keyring", default=None,
                        help="path to the agent keyring (default: ~/.dan-oss-bridge/agents.json, "
                             "or $DAN_OSS_BRIDGE_KEYRING)")
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

    sub.add_parser("channels", help="list every real channel that has received a post")

    args = parser.parse_args(argv)

    keyring_path = args.keyring or default_keyring_path()
    keyring = Keyring(keyring_path)
    # Identity is on unless explicitly disabled. When disabled, the bus is built with no keyring,
    # which restores the original unauthenticated post and unflagged read.
    bus_keyring = None if _auth_disabled() else keyring
    bus = MessageBus(args.bus or _default_bus_path(), keyring=bus_keyring)

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
            if not msgs:
                print("no real messages yet" if args.channel is None
                      else f"no real messages yet on {args.channel!r}")
                return 0
            for m in msgs:
                # verified is None when identity is off (no keyring) -> print plainly, as before.
                if m.verified is False:
                    print(f"[{m.channel}] {m.agent} (UNVERIFIED): {m.text}")
                else:
                    print(f"[{m.channel}] {m.agent}: {m.text}")
            return 0

        if args.command == "channels":
            names = bus.channels()
            if not names:
                print("no real channels yet")
                return 0
            for name in names:
                print(name)
            return 0
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
