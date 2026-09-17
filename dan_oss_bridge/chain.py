"""dan_oss_bridge.chain — whole-log tamper-evidence via a per-record hash chain.

The per-message HMAC (0.2.0) proves that one *signed* message's own content was not edited after it
was posted. It does **not** detect deletion, reordering, insertion, or replay of whole records — a
writer with file access can still drop, duplicate, or shuffle lines and the per-message signatures
of the surviving records still verify. A hash chain closes that gap: each record stores ``prev``,
the SHA-256 of the record immediately before it, so removing, reordering, or inserting any record
makes the following record's stored ``prev`` disagree with the recomputed link — and ``verify``
reports exactly where.

Two deliberate design points:

- The link binds a record's **content, its own signature, and its link to the prior record** (``prev``,
  channel, agent, text, ts, hmac). So editing a signed message breaks *both* its HMAC and the chain
  at the next record; editing an unsigned message still breaks the chain even though it has no HMAC.
- The link does **not** feed back into the HMAC. The signature stays exactly the
  ``(channel, agent, text, ts)`` HMAC shipped in 0.2.0, so signatures written before chaining
  existed still verify unchanged. Content-authenticity (HMAC) and log-integrity (chain) are separate,
  composable layers rather than one entangled scheme.

Inherent limit (documented, not a bug): a chain proves nothing was changed *within* the records it
covers, but truncating the newest records leaves a shorter, still-valid chain. Detecting a dropped
*tail* needs an external anchor (a recorded head hash), which is out of scope for a single local
file — see SECURITY.md.

Zero dependencies — standard-library ``hashlib`` and ``json`` only.
"""
from __future__ import annotations

import hashlib
import json

# The ``prev`` of the very first record in a chained log: 64 hex zeros, meaning "no record precedes
# this one". A real SHA-256 link hash is 64 hex chars too but can never be all-zero in practice, so
# genesis never collides with a real link.
GENESIS = "0" * 64


def _canonical(prev: str, channel: str, agent: str, text: str, ts: float, hmac: str) -> bytes:
    """One unambiguous byte string for a record's chained fields.

    Uses the same canonicalization discipline as ``keyring._canonical_bytes``: a JSON array with a
    fixed field order and compact separators, so the bytes are independent of the stored dict's key
    order, and a field that itself contains a delimiter cannot be rearranged to collide with a
    different tuple. ``ts`` is embedded as the same float JSON round-trips losslessly, so a writer
    and a verifier canonicalize identical bytes.
    """
    return json.dumps(
        [prev, channel, agent, text, ts, hmac],
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8", "surrogatepass")


def link_hash(prev: str, channel: str, agent: str, text: str, ts: float, hmac: str) -> str:
    """The SHA-256 (hex) that the *next* record stores as its ``prev``.

    It commits to this record's content, its own signature (``hmac``), and its link to the record
    before it (``prev``) — so tampering with any of those is detected as a broken link at the
    following record.
    """
    return hashlib.sha256(_canonical(prev, channel, agent, text, ts, hmac)).hexdigest()
