# Security Policy

## Reporting a vulnerability

If you believe you've found a security vulnerability in any DAN Systems open-source project under
the [STRATO-DAN](https://github.com/STRATO-DAN) organization, please report it privately —
**not** as a public GitHub issue.

**Email: opensource@thedubai.ai**

Please include, if you can:

- Which repository and version/commit is affected.
- A description of the vulnerability and its potential impact.
- Steps to reproduce it, or a proof-of-concept if you have one.
- Any suggested mitigation, if you have one — not required.

You're also welcome to use [GitHub's private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing/privately-reporting-a-security-vulnerability)
feature (the "Report a vulnerability" button under a repo's **Security** tab), where available, as
an alternative to email.

## What to expect

We'll acknowledge your report and work with you to understand and confirm the issue. We ask that
you give us a reasonable opportunity to investigate and address a report before any public
disclosure, and we'll keep you updated on progress as we work through it.

## Trust model (by design)

`dan-oss-bridge` is a **local, append-only** message log with **per-agent identity**. As of 0.2.0
each agent registers a local secret key, every post is signed with an HMAC-SHA256 over its
`(channel, agent, text, ts)`, and a read verifies that signature and flags anything that doesn't
verify as `UNVERIFIED`. The following are **known, intentional properties of the current design**,
not vulnerabilities — please don't file them as such:

- **Identity authenticates *across agents that don't share a key*, not against a same-user
  attacker.** The keys are stored in a local file (`~/.dan-oss-bridge/agents.json`, mode `0600`).
  Any process running as the **same operating-system user** that can read that file can sign as any
  agent whose key it holds. A verified message proves it was produced by something holding that
  agent's key; it does **not** prove the writer isn't a local same-uid attacker who read the
  keyring. This is a deliberate, documented boundary — combine the tool with OS file permissions
  and process isolation for the trust boundary you actually need.
- **No cross-message tamper-evidence or replay protection.** The per-message HMAC detects edits to
  a signed message's own content, but the log carries no message id, nonce, or hash chain — a
  writer with file access can still add, replay, reorder, or delete whole records, and a reader
  cannot detect that. Unsigned messages (older logs, or posts made with identity disabled) read as
  `UNVERIFIED` rather than being trusted.
- **`DAN_OSS_BRIDGE_NO_AUTH=1` disables identity** (unsigned posts, unflagged reads) for the
  original local-trust mode, intended for deployments where every writer of the bus file already
  trusts one another. When it is set, the `agent` field is once again just a caller-asserted label.

Corrupt-content tolerance *is* in scope and is fixed: as of 0.1.1 a single malformed line (invalid
UTF-8, non-JSON, a valid-JSON non-object, or a non-numeric timestamp) is skipped rather than
crashing every reader, and 0.2.0 keeps that tolerance while verifying signatures. A report that one
bad line can deny reads to the whole bus **is** a valid report against older versions — please
upgrade to the latest release first.

One hardening option is still held open as a **product decision** for a future version, welcome as
design discussion rather than a vulnerability report:

- a **message-id + hash-chain** to add replay- and tamper-evidence across records (the per-message
  HMAC shipped in 0.2.0 does not cover deletion or replay of whole lines).

## Scope

This policy covers the source code in DAN Systems' own public repositories. It does not cover:

- Vulnerabilities in third-party dependencies — please report those to the maintainer of that
  project directly (though we'd still appreciate a heads-up if a DAN-OSS tool bundles or pins an
  affected version). This tool in particular has zero runtime dependencies, so this class does not
  apply to it today.
- Social engineering, physical security, or denial-of-service reports.

## Supported versions

These are small, actively-developed tools without a long-term-support branch model. Please always
test against the latest published release before reporting — older versions may not receive a
fix, and the recommended remediation for any confirmed issue is to upgrade to the latest release.

Thank you for helping keep DAN Systems' open-source projects and their users safe.
