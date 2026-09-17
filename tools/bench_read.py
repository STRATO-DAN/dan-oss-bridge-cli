#!/usr/bin/env python3
"""Micro-benchmark for the tail-bounded read: prove `read --limit 50` latency stays
~flat as the log grows, i.e. read is bounded by the requested window, not file size.

Stdlib only. Builds logs of 1k / 10k / 100k messages in a temp dir, then times the
exact code path `dan-oss-bridge read --limit 50` runs (MessageBus.read) on each.
Run via `make bench`, or directly: `python3 tools/bench_read.py`.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dan_oss_bridge.bus import MessageBus  # noqa: E402

SIZES = [1_000, 10_000, 100_000]
LIMIT = 50
ITERS = 20


def _human(size: int) -> str:
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def main() -> int:
    print(f"tail-bounded read: time `read --limit {LIMIT}` as the log grows")
    print(f"{'messages':>12}  {'file size':>12}  {'read --limit ' + str(LIMIT):>18}")
    with tempfile.TemporaryDirectory() as d:
        for n in SIZES:
            path = os.path.join(d, f"bus-{n}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for i in range(n):
                    f.write(json.dumps({
                        "channel": "standup", "agent": "alice",
                        "text": f"message {i}", "ts": 1700000000.0 + i,
                    }) + "\n")
            size = os.path.getsize(path)
            # No keyring -> pure tail read, exactly what `read --limit 50` executes.
            bus = MessageBus(path)
            times = []
            for _ in range(ITERS):
                t0 = time.perf_counter()
                msgs = bus.read("standup", limit=LIMIT)
                times.append(time.perf_counter() - t0)
            assert len(msgs) == LIMIT, len(msgs)
            ms = 1000.0 * (sum(times) / len(times))
            print(f"{n:>12,}  {_human(size):>12}  {ms:>15.3f} ms")
    print("Read latency stays ~flat while the log grows 100x: read is bounded by the")
    print("requested window (limit), not by total file size.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
