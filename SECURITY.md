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

`dan-oss-bridge` is a **local, append-only, unauthenticated** message log. The following are
**known, intentional properties of the current design**, not vulnerabilities — please don't file
them as such:

- **The `agent` sender is caller-asserted.** There is no authentication, signing, or per-agent
  identity. Anyone with local write access to the bus file can post under any `agent` name. Treat
  the sender as a label, not a proof of origin.
- **No tamper-evidence or replay protection.** The log carries no message id, nonce, or hash
  chain. Anyone who can write the file can add, replay, edit, or remove messages, and a reader
  cannot detect it.
- **Intended deployment is inside a trust boundary you already control** — a single machine or a
  set of local processes that already trust one another. The bus is a coordination log for
  cooperating agents, not a security boundary between mutually-distrusting parties.

Corrupt-content tolerance *is* in scope and is fixed: as of 0.1.1 a single malformed line (invalid
UTF-8, non-JSON, a valid-JSON non-object, or a non-numeric timestamp) is skipped rather than
crashing every reader. A report that one bad line can deny reads to the whole bus **is** a valid
report against older versions — please upgrade to the latest release first.

Two hardening options are held open as **product decisions** for a future version and are welcome
as design discussion rather than vulnerability reports:

- a **per-agent key / HMAC** to give the `agent` field real sender authenticity (parity with the
  hosted DAN dashboard's protections); and
- a **message-id + hash-chain** to add replay- and tamper-evidence to the log.

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
