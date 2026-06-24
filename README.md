# ai-delegation-readiness

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md)

A reference implementation of the **4-layer prerequisites** for delegating
high-risk routine business judgments to AI agents, plus a **minimum audit log
schema** template. The framework is distilled from a real-world case study:
Ajinomoto Group's accounting AI agent for expense claim approvals, which went
into production in February 2026.

This is a **documentation-only reference implementation** — no source code
beyond Markdown and a JSON sample. The goal is to give your organization a
diagnostic checklist for "does this business judgment hold up to AI delegation?"
that you can take home and adapt.

> **Note on internal documentation language**: The documents under `docs/` and
> code comments are written in Japanese, reflecting the author's primary working
> language. This English README is the entry point; the Japanese version
> ([README.ja.md](README.ja.md)) is the canonical text.

## Who this is for

- Implementation engineers who plan to delegate accounting, approval, or
  compliance workflows to AI agents
- Business designers and accounting / management leads making the delegation
  decision
- Operations teams auditing their own AI governance design (the 4th layer:
  control and traceability)

## Main artifacts

| File | Contents |
|---|---|
| [docs/01_four_layer_framework.md](docs/01_four_layer_framework.md) | The 4-layer framework (standardization / structuring / scope / control) + efficacy measurement, with checklists |
| [docs/02_audit_log_schema.md](docs/02_audit_log_schema.md) | Minimum audit log schema (Who/When/What/Why/Result), two-tier (article-aligned baseline + J-SOX-grade design extensions), with a JSON Schema-style pseudo-definition |
| [docs/03_delegation_matrix.md](docs/03_delegation_matrix.md) | Delegation matrix on verifiability × answer-definability, with 3 scoring questions per axis |
| [examples/audit-log-sample.json](examples/audit-log-sample.json) | A dummy expense-claim audit log entry (illustrating the `escalated` decision path) |

## Self-application example (for reference)

- [docs/04_agent_loop_audit_gap.md](docs/04_agent_loop_audit_gap.md) — A
  walkthrough of how the author audited their own automation platform
  (`agent-loop`) against the 4th layer's requirements, including concrete
  `ALTER TABLE` proposals. **The portable parts of this repo are 01–03 +
  examples** — document 04 is included only as a worked example.

## How to use

1. Apply the checklist in `docs/01_four_layer_framework.md` to your target
   business process to confirm that all 4 layers + efficacy measurement are
   in place
2. When stuck on layer ③ (delegation scope), score the decision against the
   2-axis matrix in `docs/03_delegation_matrix.md`
3. Use the minimum schema in `docs/02_audit_log_schema.md` and the JSON
   sample in `examples/audit-log-sample.json` as a template for your audit log
4. To check whether your existing logging infrastructure satisfies the 4th
   layer, follow the audit method (SQL schema × 5-point mapping) demonstrated
   in `docs/04_agent_loop_audit_gap.md`

## Scope and limitations

- This is a **minimum-scope reference implementation**. Tamper resistance,
  retention periods, source-document references, and rule version pinning
  are noted as "extensions" in `docs/02`, with direction only — no
  implementation is provided
- Public information on the Ajinomoto case is thin for the 4th layer (control
  and traceability). Each document explicitly labels **【観測事実】**
  (observed facts from the case) versus **【設計提案】** (design proposals
  from this repository)
- The "76% workload reduction" figure cited in news coverage is not defined in
  the source. This repository does not warrant efficacy numbers — it only
  preserves the **observability viewpoint**

## Related references

- [Ajinomoto Financial Solutions × First Accounting: accounting AI agent in production (official announcement)](https://www.fastaccounting.jp/news/20260424/15929/)
- [Ajinomoto Group's accounting AI agent cuts workload by "76%" (ITmedia, in Japanese)](https://www.itmedia.co.jp/business/articles/2606/19/news033.html)

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
