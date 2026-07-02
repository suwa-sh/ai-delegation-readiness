# ai-delegation-readiness

![eyecatch](docs/assets/eyecatch.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md)

A diagnostic tool and extensible framework for deciding **whether a high-risk
routine business judgment is ready to be delegated to an AI agent**. Distilled
from the **published analysis** of Ajinomoto Group's accounting AI agent (in
production since February 2026).

Key features:

1. **Diagnoses delegation readiness** — it mechanically scores how far a process
   has standardized, structured and bounded its judgments, plus whether the
   claimed efficiency gain is explainable, and returns a deterministic verdict.
2. **A machine-readable single source of truth** — the four-layer framework, the
   delegation matrix and the audit-log schema are kept as definitions that AI
   agents and CI can consume directly.
3. **Extensible without forking** — each company adds its own questions and
   stricter thresholds through an overlay.

> **Glossary**:
> - **J-SOX** (Japan's internal-control reporting regime under the Financial
>   Instruments and Exchange Act) requires listed companies to evaluate and
>   report on internal control over financial reporting.
> - An **audit log** is the record of each AI judgment (who / when / what / why /
>   result) that lets you reproduce and review the decision afterwards.
> - The **four-layer framework** is the stack of prerequisites a process must
>   satisfy before delegation: standardization → structuring → delegation scope →
>   control.
> - The **efficacy axis** is a parallel viewpoint that checks whether a claimed
>   efficiency gain has an explainable denominator and baseline.
> - The **delegation matrix** scores each judgment on two axes (verifiability ×
>   answer-definability) and places it into delegate / LLM-assist / human-only.
> - An **overlay** is a company-specific extension file that adds questions or
>   strengthens thresholds without forking the canonical definitions.

> **A note on language**: Documents under `docs/` are written in Japanese (the
> author's working language). This English README is the entry point;
> [README.ja.md](README.ja.md) is the canonical text.

## Quick start (2 minutes)

No setup — pull the published image and run it. The bundled samples work out of
the box:

```bash
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 --version

docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 \
  check-readiness examples/business/sample-expense-approval.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 \
  score-delegation examples/judgments/sample-judgments.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 \
  validate-audit-log examples/audit-log-sample.json --level extended
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 \
  check-overlay examples/overlays/sample-company/extra-rules.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 list-definitions
```

`--version` prints the app version and the bundled overlay engine version, e.g.
`aidr 0.2.0 (overlay-scoring-skeleton 0.1.0)`.

Every command returns a deterministic exit code so you can gate CI on it:
**0** ok · **1** partial (yellow) · **2** block (red: gaps, SLA breach, rejected
overlay) · **3** input error.

## Usage workflow

The commands run against *your* data. Mount the directory that holds your files
into the container. A shell function keeps the rest of this guide readable:

```bash
aidr() { docker run --rm -v "$PWD:/data" -w /data \
  ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 "$@"; }
```

Grab a sample from [`examples/`](examples/) as a template, edit it with your own
values, then run the commands in this order — from diagnosis to extension.

1. **Prepare** — start your own input file from a sample (`my-business.yaml`).
2. **Diagnose the process** — fill each layer's questions with `yes` / `no`, then
   `aidr check-readiness my-business.yaml`. Fix the layer named by
   `First gate to fix` first; lower layers gate the upper ones.
3. **Score the judgments** — list your judgments and run
   `aidr score-delegation my-judgments.yaml`. GREEN delegates, YELLOW is
   LLM-assist (a human decides), RED stays human-only.
4. **Validate the audit log** — once delegation starts, check that the emitted
   log satisfies who / when / what / why / result:
   `aidr validate-audit-log my-log.json --level extended`.
5. **Extend (optional)** — add your own questions / thresholds via an overlay,
   validated by `aidr check-overlay <path>` and applied with `--overlay`.

Sample output (`check-readiness`) — `[..]` revise / `[NG]` block per layer, then
an overall verdict and the first gate to fix:

```text
Target: Expense claim approval (mid-size company, FY2026 review)

[..] L1 業務標準化層: REVISE (75%)
[NG] L2 判断構造化層: BLOCK (33%)
[..] L3 委任範囲層: REVISE (75%)
[NG] L4 統制・追跡層: BLOCK (0%)
[..] efficacy 効果測定: REVISE (75%)

Conclusion: BLOCK
  First gate to fix: layer L1
```

See [`README.ja.md`](README.ja.md#使い方想定ワークフロー) for sample output of every
command in the workflow.

## Who this is for

| If you are... | Start with... |
|---|---|
| A **business decision maker** (head of accounting, CFO, compliance lead) considering AI for a process | [`docs/01_four_layer_framework.md`](docs/01_four_layer_framework.md) — score your process with `aidr check-readiness` |
| An **engineer** designing an AI agent for high-risk approvals | [`schemas/audit-log.schema.json`](schemas/audit-log.schema.json) + [`docs/02_audit_log_schema.md`](docs/02_audit_log_schema.md) — wire the schema into your logger |
| An **operator** auditing an existing AI platform's logging | [`docs/04_audit_log_gap_check.md`](docs/04_audit_log_gap_check.md) — apply the 5-step method to your own SQL schema |
| A **consultant / proposal author** | All four `docs/` + the overlay model — clone, overlay in private, present client-specific scoring |

## What's in this repo

```
ai-delegation-readiness/
├── definitions/                 # Machine-readable canonical framework (YAML)
│   ├── four-layer.yaml          #   4 layers + efficacy axis + extension_points
│   └── delegation-matrix.yaml   #   2 axes + region map + extension_points
├── schemas/
│   └── audit-log.schema.json    # JSON Schema with $defs: minimum (A) / extended (B)
├── src/adr/                     # Python diagnostic tool (shipped as a container image)
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
    └── 04_audit_log_gap_check.md
```

## How to extend

Each company adds their own rules **via overlays**, not by forking the canonical
files. See [`examples/overlays/sample-company/extra-rules.yaml`](examples/overlays/sample-company/extra-rules.yaml)
for a template:

```yaml
version: 1
extends: four-layer-delegation-readiness

add:
  - id: "L4.ACME_Q6"
    text: Is the audit log stored in a tamper-evident store?
    weight: 1.0

strengthen:
  "L4": {revise: 0.8}       # was 0.6 — stricter only
```

Then run any diagnostic with `--overlay` (using the `aidr` shell function from
[Usage workflow](#usage-workflow) so the file is mounted):

```bash
aidr check-readiness my-business.yaml --overlay our-rules.yaml
```

The framework is reused in three ways:

- **AI agents**: load `definitions/four-layer.yaml` and
  `schemas/audit-log.schema.json` into the system prompt or tool context.
  See [`examples/skills/`](examples/skills/) for two ready-to-adapt Claude
  Code skill wrappers.
- **CI pipelines**: run `docker run --rm -v "$PWD:/data" -w /data ghcr.io/suwa-sh/ai-delegation-readiness:v0.2.0 validate-audit-log <log>` on each emitted log; gate
  on exit code.
- **Internal overlays**: keep your company-specific overlay in a private repo and
  apply with `--overlay`. The framework stays a clean upstream you can pull from.

## The framework's invariants

The canonical foundation (`definitions/*.yaml`, `schemas/*.json`) is
**framework-consistent across companies**. Overlays may only:

- **`add`** new items to a list (existing items stay read-only)
- **`strengthen`** numeric thresholds (lowering is rejected)

Anything else (delete, replace, weaken) is a merge violation and is detected
mechanically by `aidr check-overlay`. This is what makes the framework safe to
extend without forking.

## Background

The framework is distilled from a **published analysis** of the Ajinomoto Group
accounting AI agent (in production since February 2026): the maintainer wrote an
analysis article from publicly reported coverage, then extracted the framework
from that analysis. The provenance chain is: public coverage → analysis article →
this framework.

On three published tasks (receipt mandatory items, invoice scheme compliance, tax
entertainment-expense judgment), the analysis reports a domain-specialized agent
reaching **93.3%** versus **53.3%** for a vanilla LLM. The gap was closed not by a
smarter model but by **structuring the business logic** around the LLM — which is
why the framework's lower layers (standardization, structuring) matter more than
the choice of model.

**Caveat**: the widely-cited "76% workload reduction" headline has no defined
denominator, baseline, or scope in the source articles. This repository does not
warrant efficacy figures; it preserves the **observability viewpoint**
(`docs/01` efficacy axis).

### Source

- **Analysis article** (Japanese, the immediate source from which the framework was distilled): [「味の素の経理AIエージェントに学ぶ 承認業務をAIに委任する前提条件」](https://suwa-sh.github.io/zenn-contents/articles/ajinomoto-accounting-agent_20260621/)

### Coverage cited in the analysis article

- [Ajinomoto Financial Solutions × First Accounting press release (2026-04-24)](https://www.fastaccounting.jp/news/20260424/15929/)
- [ITmedia "76% workload reduction" coverage (2026-06-19, Japanese)](https://www.itmedia.co.jp/business/articles/2606/19/news033.html)

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
