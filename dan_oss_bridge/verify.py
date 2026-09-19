"""dan_oss_bridge.verify — audit a whole bus log for tamper-evidence.

``verify_log(path, keyring)`` walks the entire log in file order and returns a ``LogReport``: a
per-record verdict plus a whole-log integrity summary. It answers two independent questions for
every record —

- **Content authenticity** (the 0.2.0 HMAC): is this record signed, and does the signature verify
  against the sending agent's current key? Verdicts: ``ok`` (verifies), ``forged`` (has a signature
  that does not verify, or is from an agent this keyring has no key for), ``unsigned`` (no signature
  — a local-trust post or a pre-identity record), or ``corrupt`` (the line could not be parsed).
- **Log integrity** (the hash chain, when present): does each record's stored ``prev`` match the
  recomputed link of the record before it? A deletion, reorder, insertion, or in-place edit breaks
  the chain at the following record, and the report names the first line where it breaks.

Unlike ``MessageBus.read`` — which returns a most-recent *window* and tolerates individual bad lines
— verify reads the **whole** file from line 1, because integrity is a property of the entire log,
not of a window. It is still tolerant: a corrupt line is reported as its own verdict rather than
raising.

Zero dependencies — standard library only.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path

from .chain import GENESIS, link_hash
from .keyring import Keyring, verify as _verify_hmac


@dataclass(frozen=True)
class RecordVerdict:
    """One record's verdict. ``line`` is 1-based (matches an editor's line number)."""
    line: int
    channel: str
    agent: str
    text: str
    # "ok" | "forged" | "unsigned" | "corrupt"
    auth: str
    # True only when this record is chained (carries a ``prev``) and its link is intact. False when
    # chained but the link is broken. None when the record is not part of a chain.
    chain_ok: "bool | None"
    # A short human note when something is off (e.g. why it broke), else "".
    note: str = ""


@dataclass
class LogReport:
    path: str
    total: int = 0
    ok: int = 0
    forged: int = 0
    unsigned: int = 0
    corrupt: int = 0
    replayed: int = 0
    missing: bool = False
    # Whether any record in the log carried a ``prev`` (i.e. the log is chained at all).
    chain_present: bool = False
    # True when the chain is present and every link verified; None when no chain is present.
    chain_intact: "bool | None" = None
    # 1-based line of the first broken link, or None.
    first_break_line: "int | None" = None
    # Whether a keyring was available to check signatures at all.
    keyring_available: bool = False
    records: list = field(default_factory=list)

    @property
    def tampered(self) -> bool:
        """True when there is positive evidence of tampering or corruption: a broken chain link, a
        forged signature, or an unparseable line. Unsigned-but-otherwise-fine records are NOT
        tampering (they are allowed in local-trust mode) — see ``clean``/``--strict``."""
        return (
            (self.chain_present and self.chain_intact is False)
            or self.forged > 0
            or self.corrupt > 0
        )

    def clean(self, strict: bool = False) -> bool:
        """True when the log shows no tampering. With ``strict``, any unsigned or unverified record
        also fails (use in a deployment that expects every message to be signed)."""
        if self.tampered or self.missing or self.replayed:
            return False
        if strict and (self.unsigned > 0 or self.forged > 0):
            return False
        return True


def _extract(raw: str):
    """Parse one raw log line for verification.

    Returns ``(fields, has_prev)`` where ``fields`` is the dict of record fields (channel/agent/
    text/ts/hmac/prev, defaulted and type-guarded exactly like ``MessageBus._parse_line``) and
    ``has_prev`` says whether the record actually carried a ``prev`` key (so an absent ``prev`` is
    distinguished from a stored empty one). Returns ``None`` for a blank line, and raises nothing —
    a non-blank line that is not a usable JSON object is signalled by returning ``"corrupt"``.
    """
    line = raw.strip()
    if not line:
        return None
    try:
        d = json.loads(line)
    except (ValueError, json.JSONDecodeError):
        return "corrupt"
    if not isinstance(d, dict):
        return "corrupt"
    try:
        ts = float(d.get("ts", 0.0))
    except (TypeError, ValueError):
        return "corrupt"
    if not math.isfinite(ts):
        return "corrupt"
    mac = d.get("hmac", "")
    if not isinstance(mac, str):
        mac = ""
    prev = d.get("prev", "")
    if not isinstance(prev, str):
        prev = ""
    fields = {
        "channel": d.get("channel", "") if isinstance(d.get("channel", ""), str) else "",
        "agent": d.get("agent", "") if isinstance(d.get("agent", ""), str) else "",
        "text": d.get("text", "") if isinstance(d.get("text", ""), str) else "",
        "ts": ts,
        "hmac": mac,
        "prev": prev,
    }
    return fields, ("prev" in d and isinstance(d.get("prev"), str))


def verify_log(path: str | Path, keyring: Keyring | None = None) -> LogReport:
    """Audit the whole log at ``path``. ``keyring`` (when given) is used to check each signature;
    without one, signatures are reported as present/absent but never marked verified or forged."""
    p = Path(path)
    report = LogReport(path=str(p), keyring_available=keyring is not None)
    if not p.is_file():
        report.missing = True
        return report

    # ``expected`` is the link hash the NEXT chained record must store as its ``prev``. It starts at
    # GENESIS and, after each record, becomes that record's own link — so a chained record is intact
    # iff its stored ``prev`` equals ``expected`` at that point. A corrupt line makes ``expected``
    # unknown (None), which correctly breaks any chained record that follows it.
    expected: "str | None" = GENESIS
    seen_signed = set()

    with p.open("r", encoding="utf-8", errors="replace") as f:
        for i, raw in enumerate(f, start=1):
            parsed = _extract(raw)
            if parsed is None:
                continue  # blank line — the writer never emits one; ignore rather than fault
            if parsed == "corrupt":
                report.total += 1
                report.corrupt += 1
                report.records.append(RecordVerdict(
                    line=i, channel="", agent="", text="", auth="corrupt", chain_ok=None,
                    note="line is not a usable JSON record",
                ))
                expected = None  # continuity is lost across an unparseable line
                continue

            fields, has_prev = parsed
            report.total += 1

            # --- content authenticity (HMAC) ---
            auth, note = _classify_auth(fields, keyring)
            if fields["hmac"]:
                fingerprint = (fields["channel"], fields["agent"], fields["text"], fields["ts"], fields["hmac"])
                if fingerprint in seen_signed:
                    report.replayed += 1
                    note = "duplicate signed record: possible replay; " + note
                seen_signed.add(fingerprint)
            if auth == "ok":
                report.ok += 1
            elif auth == "forged":
                report.forged += 1
            else:  # unsigned
                report.unsigned += 1

            # --- log integrity (hash chain) ---
            chain_ok: "bool | None" = None
            if has_prev:
                report.chain_present = True
                if expected is not None and fields["prev"] == expected:
                    chain_ok = True
                else:
                    chain_ok = False
                    if report.first_break_line is None:
                        report.first_break_line = i
                    detail = "no readable record precedes it" if expected is None else \
                        "stored prev does not match the preceding record"
                    note = (note + "; " if note else "") + f"chain break: {detail}"

            # Whatever this record is, compute the link the next record must match.
            expected = link_hash(
                fields["prev"], fields["channel"], fields["agent"],
                fields["text"], fields["ts"], fields["hmac"],
            )

            report.records.append(RecordVerdict(
                line=i, channel=fields["channel"], agent=fields["agent"], text=fields["text"],
                auth=auth, chain_ok=chain_ok, note=note,
            ))

    if report.chain_present:
        report.chain_intact = report.first_break_line is None
    return report


def _classify_auth(fields: dict, keyring: Keyring | None):
    """Return ``(auth, note)`` for one record's signature. ``ok`` when a signature verifies against
    the agent's key; ``forged`` when a signature is present but does not verify (bad key, unknown
    agent, or tampered content); ``unsigned`` when there is no signature at all."""
    mac = fields["hmac"]
    if not mac:
        return "unsigned", ""
    if keyring is None:
        # A signature is present but we have no keys to check it against. Report it as unsigned for
        # counting purposes but say why in the note, so a keyless audit never claims "forged".
        return "unsigned", "signature present but not checked (no keyring)"
    key = keyring.get(fields["agent"])
    if key is None:
        return "forged", f"no key for agent {fields['agent']!r} — cannot authenticate"
    # Sealed (v2) records are checked against their stored chain position first, legacy (v1)
    # second — so a sealed record copied to a new tail fails (position mismatch on both forms),
    # while every pre-seal signature verifies exactly as before. See keyring._canonical_bytes.
    # Success stays note-free (a verifying record needs no annotation); failures explain below.
    if _verify_hmac(key, fields["channel"], fields["agent"], fields["text"], fields["ts"], mac, fields["prev"]):
        return "ok", ""
    if fields["prev"]:
        return "forged", "signature does not match the record content at its stored chain position"
    return "forged", "signature does not match the record content"


def format_report(report: LogReport, strict: bool = False) -> str:
    """A human-readable audit. One line per record, then a summary and the whole-log verdict."""
    lines: list[str] = []
    for r in report.records:
        chain = "-" if r.chain_ok is None else ("linked" if r.chain_ok else "BROKEN")
        label = {"ok": "ok", "forged": "FORGED", "unsigned": "unsigned", "corrupt": "CORRUPT"}[r.auth]
        head = f"  line {r.line}: {label:8} chain={chain:6}"
        if r.auth == "corrupt":
            body = "(unparseable line)"
        else:
            body = f"[{_safe_terminal(r.channel)}] {_safe_terminal(r.agent)}: {_safe_terminal(r.text)}"
        suffix = f"  <- {_safe_terminal(r.note)}" if r.note else ""
        lines.append(f"{head} {body}{suffix}")

    if report.chain_present:
        chain_verdict = ("chain intact" if report.chain_intact
                         else f"CHAIN BROKEN at line {report.first_break_line}")
    else:
        chain_verdict = "no hash chain (unchained log — content signatures only)"

    lines.append("")
    lines.append(
        f"{report.total} record(s): {report.ok} ok, {report.forged} forged, "
        f"{report.unsigned} unsigned, {report.corrupt} corrupt"
    )
    if not report.keyring_available:
        lines.append("(no keyring available — signatures were not checked)")
    lines.append(chain_verdict)
    if report.missing:
        lines.append("MISSING LOG: no integrity assessment is possible")
    if report.replayed:
        lines.append(f"DUPLICATE SIGNED RECORDS: {report.replayed}; possible replay")
    verdict = ("clean" if report.clean(strict=strict)
               else "TAMPERING DETECTED" if report.tampered
               else "not clean (missing log, duplicate signatures, or strict verification failure)")
    # A non-strict "clean" over unsigned records is local-trust only — say so on the verdict
    # line itself, so it can never be read as "every record authenticated".
    if verdict == "clean" and not strict and report.unsigned > 0:
        verdict = (f"clean (local-trust only: {report.unsigned} unsigned record(s) present "
                   f"— use --strict to require signatures)")
    lines.append("VERDICT: " + verdict)
    return "\n".join(lines)


def report_to_dict(report: LogReport, strict: bool = False) -> dict:
    """The same report as a JSON-serializable dict, for ``verify --json`` (scriptable/CI use)."""
    return {
        "path": report.path,
        "total": report.total,
        "ok": report.ok,
        "forged": report.forged,
        "unsigned": report.unsigned,
        "corrupt": report.corrupt,
        "missing": report.missing,
        "replayed": report.replayed,
        "chain_present": report.chain_present,
        "chain_intact": report.chain_intact,
        "first_break_line": report.first_break_line,
        "keyring_available": report.keyring_available,
        "tampered": report.tampered,
        "clean": report.clean(strict=strict),
        "records": [
            {
                "line": r.line,
                "channel": r.channel,
                "agent": r.agent,
                "text": r.text,
                "auth": r.auth,
                "chain_ok": r.chain_ok,
                "note": r.note,
            }
            for r in report.records
        ],
    }


def _safe_terminal(value: str) -> str:
    return "".join(char if char.isprintable() else f"\\u{ord(char):04x}" for char in value)
