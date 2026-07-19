# ai-delegation-readiness

![OGP](docs/assets/ogp.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md)

A diagnostic tool and extensible framework for deciding **whether a high-risk
routine business judgment is ready to be delegated to an AI agent** — and, once
it is, **how each task is handed over and scored**. Distilled from the
**published analysis** of Ajinomoto Group's accounting AI agent (in production
since February 2026).

Key features:

1. **Maps where to start before you delegate** — it screens task groups on three
   axes (theoretical exposure / human necessity / demand elasticity) into the
   four AI-transition types (growth / high automation / reorganization / minimal
   change), ordered by delegation-design priority. The top priority is
   *reorganization* (humans stay central but headcount demand may shrink — the
   zone that needs the most design), and every type carries a recommended
   decision order that puts headcount **last**.
2. **Diagnoses delegation readiness on two fronts** — it mechanically scores how
   far a *process* has standardized, structured and bounded its judgments (plus
   whether the claimed efficiency gain is explainable), and — in parallel —
   whether the *organization* can absorb the delegation (authority to pull the
   plug, a literacy layer to receive the tool, a knowledge-transfer contract, a
   bus-factor countermeasure). It returns a deterministic verdict for each, so
   "the process is delegable but the organization is not ready yet" shows up as
   its own gap instead of hiding behind a green process score.
3. **Checks how each delegated task is run** — once readiness passes, it scores a
   task's execution contract on four elements (intent, boundary, evidence,
   scorer), so a task is not handed to an agent with an unstated pass condition,
   no escalation path, or an AI judge that scores itself against a single rubric.
4. **A machine-readable single source of truth** — the transition screening, the
   four-layer framework, the delegation matrix, the task-contract rubric and the
   audit-log schema are kept as definitions that AI agents and CI can consume
   directly.
5. **Extensible without forking** — each company adds its own questions and
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
> - The **organization axis** is a parallel viewpoint that checks whether the
>   organization (not the process) is ready: withdrawal authority, a
>   company-wide literacy layer, a knowledge-transfer contract, an
>   incremental-split design, and a bus-factor countermeasure.
> - **Bus factor** is the number of people who would have to be lost before a
>   project stalls; a bus factor of 1 means a single person is a single point of
>   failure.
> - A **knowledge-transfer contract** makes internalization (the vendor's
>   know-how moving in-house) a measured KPI, rather than paying only for a
>   delivered artifact.
> - The **delegation matrix** scores each judgment on two axes (verifiability ×
>   answer-definability) and places it into delegate / LLM-assist / human-only.
> - The **task-contract execution rubric** is the phase *after* readiness: it
>   checks how one delegated task is handed over and scored, across four elements
>   — intent, boundary, evidence, scorer.
> - **iRULER** (CHI 2026) is a rubric-of-rubric double-evaluation: when an AI is
>   the scorer, it evaluates the scoring rubric itself, so the AI judge is not
>   grading against a single visible rubric it can optimize (Goodhart).
> - An **overlay** is a company-specific extension file that adds questions or
>   strengthens thresholds without forking the canonical definitions.
> - The **AI-transition screening** is the phase *before* delegation scoring: it
>   sorts task groups into growth / high automation / reorganization / minimal
>   change to decide where delegation design should start (a simplified lens
>   derived from OpenAI's EU AI Jobs Transition Framework).
> - **HITL** (human-in-the-loop) keeps a human on the execution path for the
>   final decision. Work affecting rights, finances, health, or regulated
>   matters is treated as a default HITL domain by this tool.

> **A note on language**: Documents under `docs/` are written in Japanese (the
> author's working language). This English README is the entry point;
> [README.ja.md](README.ja.md) is the canonical text.

## Quick start (2 minutes)

No setup — pull the published image and run it. The bundled samples work out of
the box:

```bash
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 --version

docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 \
  screen-transition examples/task-groups/sample-task-groups.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 \
  check-readiness examples/business/sample-expense-approval.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 \
  score-delegation examples/judgments/sample-judgments.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 \
  validate-audit-log examples/audit-log-sample.json --level extended
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 \
  check-overlay examples/overlays/sample-company/extra-rules.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 list-definitions
```

`--version` prints the app version and the bundled overlay engine version, e.g.
`aidr 0.7.0 (overlay-scoring-skeleton 0.1.0)`.

Every command returns a deterministic exit code so you can gate CI on it:
**0** ok · **1** partial (yellow) · **2** block (red: gaps, SLA breach, rejected
overlay) · **3** input error.
The exception is `screen-transition`: screening is a classification, not a
pass/fail gate, so it exits **0** on success whatever the types are (missing
answers and overlay violations still exit **3**).

## Usage workflow

The commands run against *your* data. Mount the directory that holds your files
into the container. A shell function keeps the rest of this guide readable:

```bash
aidr() { docker run --rm -v "$PWD:/data" -w /data \
  ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 "$@"; }
```

Grab a sample from [`examples/`](examples/) as a template, edit it with your own
values, then run the commands in this order — from diagnosis to extension.

1. **Prepare** — start your own input files from the samples
   (`my-task-groups.yaml`, `my-business.yaml`).
2. **Map where to start** — list your task groups, answer the three axes'
   questions, then `aidr screen-transition my-task-groups.yaml`. The output is
   ordered by delegation-design priority: *reorganization* first (role redesign
   needed), *high automation* feeds step 4's judgment scoring. Groups touching
   rights / finances / health / regulated matters carry a `[HITL]` marker
   whatever their type. Every question must be answered — missing answers are an
   input error, so an unanswered human-necessity question can never tip a group
   toward the humans-not-needed side. See
   [`docs/09_transition_screening.md`](docs/09_transition_screening.md).
3. **Diagnose the process and the organization** — fill each layer's questions
   with `yes` / `no`, then `aidr check-readiness my-business.yaml`. The four
   layers stack (fix the layer named by `First gate to fix` first; lower layers
   gate the upper ones), while the efficacy and organization axes are scored in
   parallel — an organization gap does not gate the layers, it stands on its own.
4. **Score the judgments** — list your judgments and run
   `aidr score-delegation my-judgments.yaml`. GREEN delegates, YELLOW is
   LLM-assist (a human decides), RED stays human-only.
5. **Check the task contract** — for a task you decided to delegate, declare its
   intent / boundary / evidence / scorer and run
   `aidr check-task-contract my-contract.yaml`. GREEN is ready to run, YELLOW has
   a thin element, RED blocks (a missing element, or an AI judge with no iRULER
   double-evaluation). Start from
   [`examples/task-contracts/sample-green.yaml`](examples/task-contracts/sample-green.yaml).
6. **Validate the audit log** — once delegation starts, check that the emitted
   log satisfies who / when / what / why / result:
   `aidr validate-audit-log my-log.json --level extended`.
7. **Extend (optional)** — add your own questions / thresholds via an overlay,
   validated by `aidr check-overlay <path>` and applied with `--overlay`.
   A bundled domain overlay for high-stakes professional work (IP / legal /
   pharma) adds a hard prerequisite gate (L5) and cautious-side matrix
   thresholds — see
   [`docs/07_high_stakes_domain_overlay.md`](docs/07_high_stakes_domain_overlay.md):

   ```bash
   aidr check-readiness examples/business/sample-ip-agent-readiness.yaml \
     --overlay examples/overlays/high-stakes-domain/four-layer.yaml
   # => L1-L4 all PASS, yet one missing prerequisite blocks at L5

   aidr score-delegation examples/judgments/sample-ip-judgments.yaml \
     --overlay examples/overlays/high-stakes-domain/delegation-matrix.yaml
   # => boundary cases (2/3 on an axis) drop from green to yellow / red
   ```

   A second bundled overlay scores **insourcing judgment responsibility** — the
   "which upstream judgments a company keeps in-house" question that *precedes*
   delegation — as a parallel axis `L_insourcing` (5 questions). It does not gate
   L1-L4; it surfaces "process delegable, but insourcing judgment responsibility
   not established" as its own verdict. See
   [`docs/08_insourcing_judgment_overlay.md`](docs/08_insourcing_judgment_overlay.md):

   ```bash
   aidr check-readiness examples/business/sample-insourcing-readiness.yaml \
     --overlay examples/overlays/insourcing-judgment/four-layer.yaml
   # => L1-L4 and organization all PASS, yet a missing in-house owner is REVISE/BLOCK
   ```

Sample output (`check-readiness`) — `[OK]` pass / `[..]` revise / `[NG]` block per
layer and axis, then an overall verdict. This run uses the bundled
[`examples/business/ajinomoto-discovery-team.yaml`](examples/business/ajinomoto-discovery-team.yaml),
a team that has nailed the *process* but not the *organization*:

```text
Target: New-business discovery team (small full-stack, exploration phase)

[OK] L1 業務標準化層: PASS (100%)
[OK] L2 判断構造化層: PASS (100%)
[OK] L3 委任範囲層: PASS (100%)
[OK] L4 統制・追跡層: PASS (100%)
[OK] efficacy 効果測定: PASS (100%)
[NG] organization 組織 readiness層: BLOCK (33%)
    no: organization.C2, organization.C4, organization.C5, organization.C6

Conclusion: BLOCK
```

Every process layer passes, yet the verdict is BLOCK: the organization axis
surfaces the missing literacy layer (C2), knowledge-transfer contract (C4),
incremental-split design (C5) and bus-factor countermeasure (C6). When a layer
is the first gate instead, the output also prints `First gate to fix`.

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
│   ├── transition-screening.yaml #  3 axes + 4 transition types map + extension_points
│   ├── four-layer.yaml          #   4 layers + efficacy & organization axes + extension_points
│   ├── delegation-matrix.yaml   #   2 axes + region map + extension_points
│   └── task-contract.yaml       #   4 execution-rubric elements + gate policy + extension_points
├── schemas/
│   └── audit-log.schema.json    # JSON Schema with $defs: minimum (A) / extended (B)
├── src/adr/                     # Python diagnostic tool (shipped as a container image)
├── bin/aidr                     # CLI entry point (single command, 7 subcommands)
├── examples/
│   ├── task-groups/             # Sample input for screen-transition (all 4 types + HITL)
│   ├── business/                # Sample input for check-readiness (ajinomoto-discovery-team / sample-ip-agent-readiness / sample-insourcing-readiness)
│   ├── judgments/               # Sample input for score-delegation (generic / 4 patent-work steps)
│   ├── task-contracts/          # Sample input for check-task-contract (green / red-ai-judge)
│   ├── audit-log-sample.json    # Sample audit log (extended-level valid)
│   ├── overlays/                # Sample overlays (Acme Corp; organization-readiness-ajinomoto; high-stakes-domain; insourcing-judgment)
│   └── skills/                  # Three Claude Code skill samples
└── docs/
    ├── 01_four_layer_framework.md
    ├── 02_audit_log_schema.md
    ├── 03_delegation_matrix.md
    ├── 04_audit_log_gap_check.md
    ├── 05_organization_axis.md
    ├── 06_task_contract_execution_rubric.md
    ├── 07_high_stakes_domain_overlay.md
    ├── 08_insourcing_judgment_overlay.md
    └── 09_transition_screening.md
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

Overlays work on the organization axis too. See
[`examples/overlays/organization-readiness-ajinomoto.yaml`](examples/overlays/organization-readiness-ajinomoto.yaml),
which adds a company-specific organization question and raises the organization
bar (`revise` 0.66 → 0.83) to reflect the evidence that organizational readiness
is hard to reach.

Then run any diagnostic with `--overlay` (using the `aidr` shell function from
[Usage workflow](#usage-workflow) so the file is mounted):

```bash
aidr check-readiness my-business.yaml --overlay our-rules.yaml
```

The framework is reused in three ways:

- **AI agents**: load `definitions/four-layer.yaml` and
  `schemas/audit-log.schema.json` into the system prompt or tool context.
  See [`examples/skills/`](examples/skills/) for three ready-to-adapt Claude
  Code skill wrappers.
- **CI pipelines**: run `docker run --rm -v "$PWD:/data" -w /data ghcr.io/suwa-sh/ai-delegation-readiness:v0.7.0 validate-audit-log <log>` on each emitted log; gate
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
