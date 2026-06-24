# Security Policy

## Reporting a Vulnerability

This repository is a **documentation-only reference implementation** — it
contains Markdown files and a JSON example, with no executable code.
The realistic threat surface is therefore narrow.

If you discover any of the following, please report it via **GitHub Private
Vulnerability Reporting** (Security tab → "Report a vulnerability" on this
repository):

- A credible secret or credential accidentally committed to this repository
  (e.g. a real internal URL that should be a placeholder, an API token)
- A factual error in the audit log schema or 4-layer framework that, if
  followed as-is, would cause a clear compliance or governance gap (e.g. a
  J-SOX-relevant field omitted in a way that makes audit infeasible)
- A linkable misrepresentation of the cited case studies that could
  mislead readers (especially around regulatory framing)

Please **do not** open a public issue for the above.

## Out of Scope

The following are documented design choices, not security issues:

- The audit log "extensions" (tamper resistance, retention periods, source
  document references, delegation lifecycle) are intentionally not
  implemented. `docs/02_audit_log_schema.md` flags them as direction-only
- The "76% workload reduction" cited from news coverage is acknowledged as
  undefined in `docs/01_four_layer_framework.md` — quoting it without that
  caveat is on the consumer side, not this repository
- Disagreement with the recommended scoring rules in
  `docs/03_delegation_matrix.md`. The 3-question / majority-yes rubric is a
  design proposal labelled as such; alternative rubrics are welcome via
  normal issues or PRs

## Response

I am a single maintainer; please allow up to **14 days** for an initial
response. Acknowledged reports will be addressed in a follow-up commit, with
credit at the reporter's discretion.
