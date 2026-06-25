# ai-delegation-readiness

![eyecatch](docs/assets/eyecatch.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md)

A diagnostic tool and extensible framework for deciding **whether a
high-risk routine business judgment is ready to be delegated to an AI
agent**. Distilled from a real production case (Ajinomoto Group's
accounting AI agent, in production since February 2026).

You get three things from a clone:

1. **A CLI diagnostic** — `bin/aidr check-readiness` / `score-delegation` /
   `validate-audit-log` — runs in under a minute.
2. **Machine-readable framework** (`definitions/*.yaml`, `schemas/*.json`)
   that AI agents can load as system context, and CI pipelines can call
   directly.
3. **Overlay extension points** so each company can add their own
   questions and stricter thresholds **without forking the framework**.

> **A note on language**: Documents under `docs/` are written in Japanese
> (the author's working language). This English README is the entry point;
> [README.ja.md](README.ja.md) is the canonical text.

## Quick start (3 minutes)

```bash
git clone https://github.com/suwa-sh/ai-delegation-readiness.git
cd ai-delegation-readiness
pip install -r requirements.txt

# 1. Score a sample business against the 4-layer + efficacy framework
bin/aidr check-readiness examples/business/sample-expense-approval.yaml

# 2. Score five judgments against the delegation matrix
bin/aidr score-delegation examples/judgments/sample-judgments.yaml

# 3. Validate an audit log against the J-SOX-grade extended schema
bin/aidr validate-audit-log examples/audit-log-sample.json --level extended

# 4. Check an overlay's merge rules (additions and strengthening only)
bin/aidr check-overlay examples/overlays/sample-company/extra-rules.yaml

# 5. Inspect what definitions and overlays are loaded
bin/aidr list-definitions
```

Each command returns a deterministic exit code (0 ok, 1 partial / yellow,
2 block / red, 3 overlay error) so you can gate CI on the diagnostic
outcome.

## Who this is for

| If you are... | Start with... |
|---|---|
| A **business decision maker** (head of accounting, CFO, compliance lead) considering AI for a process | [`docs/01_four_layer_framework.md`](docs/01_four_layer_framework.md) — score your process with `bin/aidr check-readiness` |
| An **engineer** designing an AI agent for high-risk approvals | [`schemas/audit-log.schema.json`](schemas/audit-log.schema.json) + [`docs/02_audit_log_schema.md`](docs/02_audit_log_schema.md) — wire the schema into your logger |
| An **operator** auditing an existing AI platform's logging | [`docs/04_agent_loop_audit_gap.md`](docs/04_agent_loop_audit_gap.md) — apply the 5-step method to your own SQL schema |
| A **consultant / proposal author** | All four `docs/` + the overlay extension model — clone, fork in private, present client-specific scoring |

## What's in this repo

```
ai-delegation-readiness/
├── definitions/                 # Machine-readable canonical framework (YAML)
│   ├── four-layer.yaml          #   4 layers + efficacy axis + extension_points
│   └── delegation-matrix.yaml   #   2 axes + region map + extension_points
├── schemas/
│   └── audit-log.schema.json    # JSON Schema with $defs: minimum (A) / extended (B)
├── src/adr/                     # Python diagnostic tool (no pip install required)
├── bin/aidr                     # CLI entry point (single command, 5 subcommands)
├── examples/
│   ├── business/                # Sample input for check-readiness
│   ├── judgments/               # Sample input for score-delegation
│   ├── audit-log-sample.json    # Sample audit log (extended-level valid)
│   ├── overlays/                # Sample overlay (Acme Corp)
│   └── skills/                  # Two Claude Code skill samples
└── docs/
    ├── 01_four_layer_framework.md
    ├── 02_audit_log_schema.md
    ├── 03_delegation_matrix.md
    └── 04_agent_loop_audit_gap.md
```

## How to extend (the framework's intent)

Each company adds their own rules **via overlays**, not by forking the
canonical files. See [`examples/overlays/sample-company/extra-rules.yaml`](examples/overlays/sample-company/extra-rules.yaml)
for a template:

```yaml
version: 1
extends: four-layer-delegation-readiness

layers:
  - id: L4
    add_questions:
      - id: ACME_L4Q6
        text: Is the audit log stored in a tamper-evident store?
        weight: 1.0
    strengthen_thresholds:
      revise: 0.8       # was 0.6 — stricter only
```

Then run any diagnostic with `--overlay`:

```bash
bin/aidr check-readiness mybiz.yaml --overlay /path/to/our-rules.yaml
```

**Three ways the framework gets reused**:

- **AI agents**: load `definitions/four-layer.yaml` and
  `schemas/audit-log.schema.json` into the system prompt or tool context.
  See [`examples/skills/`](examples/skills/) for two ready-to-adapt Claude
  Code skill wrappers.
- **CI pipelines**: call `bin/aidr validate-audit-log` on each emitted
  log; gate on exit code.
- **Internal forks**: keep your company-specific overlay in a private repo
  and apply with `--overlay`. The framework stays a clean upstream that
  you can pull updates from.

## The framework's invariants

The canonical foundation (`definitions/*.yaml`, `schemas/*.json`) is
**framework-consistent across companies**. Overlays may only:

- **`add`** new items to a list (existing items stay read-only)
- **`strengthen`** numeric thresholds (lowering is rejected)

Anything else (delete, replace, weaken) is a merge violation and is
detected mechanically by `aidr check-overlay`. This is what makes the
framework safe to extend without forking.

## Background

The framework is distilled from the **Ajinomoto Financial Solutions (AFS)
× First Accounting accounting AI agent**, which went into production in
February 2026. The public case study reports a domain-specialized agent
achieving **93.3%** versus **53.3%** for a vanilla LLM on three published
tasks (receipt mandatory items, invoice scheme compliance, tax
entertainment-expense judgment).

The case demonstrates that the gap was not closed by a smarter model but
by **structuring the business logic** around the LLM. This is why the
framework's lower layers (standardization, structuring) matter more than
the choice of model.

**Caveats reproduced honestly**: The widely-cited "76% workload
reduction" headline is **not defined in the source article** — denominator,
baseline, and scope are unstated. This repository does not warrant
efficacy figures; it preserves the **observability viewpoint**
(`docs/01` efficacy axis).

### Original sources

- [Ajinomoto Financial Solutions × First Accounting press release (2026-04-24)](https://www.fastaccounting.jp/news/20260424/15929/)
- [ITmedia "76% workload reduction" coverage (2026-06-19, Japanese)](https://www.itmedia.co.jp/business/articles/2606/19/news033.html)

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
