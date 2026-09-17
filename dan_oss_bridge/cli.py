"""dan_oss_bridge.cli — the real CLI: `dan-oss-bridge post|read|channels`."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .bus import MessageBus


def _default_bus_path() -> str:
    return os.environ.get("DAN_OSS_BRIDGE_BUS") or str(Path.home() / ".dan-oss-bridge" / "bus.jsonl")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dan-oss-bridge", description="A unified agent communication bus.")
    parser.add_argument("--bus", default=None, help="path to the real bus file (default: ~/.dan-oss-bridge/bus.jsonl)")
    sub = parser.add_subparsers(dest="command", required=True)

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
    bus = MessageBus(args.bus or _default_bus_path())

    try:
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
        # bad input (empty channel/agent, oversize text) — a clear message, not a traceback
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
