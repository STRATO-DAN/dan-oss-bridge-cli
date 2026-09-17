# Benchmarks

`dan-oss-bridge` reads the log **tail-first**: a `read --limit N` seeks backward from the end of the
file and stops once it has `N` messages, so its cost is bounded by the requested window `N`, not by
the total size of the log. This is the property that lets the bus back a long-lived, ever-growing
log without reads getting slower over time.

## Tail-bounded read: `read --limit 50` as the log grows

Each row builds a fresh log of the given size, then times the exact code path
`dan-oss-bridge read --limit 50` runs (`MessageBus.read`), averaged over 20 iterations.

| messages | file size | `read --limit 50` |
|---------:|----------:|------------------:|
|    1,000 |   81.9 KB |          0.113 ms |
|   10,000 |  829.0 KB |          0.118 ms |
|  100,000 |    8.2 MB |          0.139 ms |

The log grows **100×** (81.9 KB → 8.2 MB) while read latency stays essentially flat (~0.11–0.14 ms):
the read is bounded by its `--limit` window, not by the file size. A naive whole-file read would grow
roughly linearly with the file instead.

## Reproduce

```bash
make bench
```

(Equivalently: `python3 tools/bench_read.py`.) Standard library only — no dependencies to install,
and it runs in well under a second.

## Machine note

Measured on Python 3.14.6, macOS 26.6.2 (Darwin arm64). Absolute numbers vary by machine and disk
cache; the flat-across-log-size shape is the point, and it reproduces anywhere.
