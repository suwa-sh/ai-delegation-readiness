# ai-delegation-readiness

![OGP](docs/assets/ogp.png)

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

> 🇯🇵 日本語版は [README.ja.md](README.ja.md)

## What this is (in one minute)

A diagnostic tool and extensible framework for deciding **whether a business
judgment is ready to be delegated to an AI agent** — by scoring, not by gut
feeling.

- **AI agent** = an AI program that carries out judgments and work on
  instruction
- **Delegation** = handing a judgment a human used to make over to an AI.
  Responsibility stays with the human side, which is why the preconditions
  deserve a check before you delegate

The tool breaks that check into a **main line of 6 steps plus an optional
extension**. Each step answers one question:

| Step | Question | Command |
|---|---|---|
| 1 | Which task groups should we start with? | `aidr screen-transition` |
| 2 | Can this process withstand delegation? | `aidr check-readiness` |
| 3 | Which individual judgments do we delegate? | `aidr score-delegation` |
| 4 | How is each task handed over, and who scores it? | `aidr check-task-contract` |
| 5 | Can the record be verified afterwards? | `aidr validate-audit-log` |
| 6 | Can humans afford to own this AI-generated patch? | `aidr check-patch-ownership` |
| Ext. | How do we add company-specific rules? (optional) | `aidr check-overlay` + `--overlay` |
| Ext. | How do we review accept/discard decisions afterwards? (optional) | `aidr summarize-patch-decisions` |
| Ext. | Can the receiving organization detect, contain, and escalate agentic failures? (optional) | `aidr assess-risk-architecture` |

The bundled samples are connected by the story of a fictional mid-size
manufacturer, **Midori Seiki Co., Ltd.** The story includes a timeline — the
first diagnosis comes back **BLOCK**, the team fixes the gaps, and only a
**PASS** re-diagnosis unlocks the next step
(canonical profile: [`examples/README.md`](examples/README.md), in Japanese).

```mermaid
flowchart LR
    s1["1 screening"] --> s2["2 readiness check<br/>fix and re-check on BLOCK"]
    s2 --> s3["3 judgment scoring"]
    s3 --> s4["4 task contract"]
    s4 --> s5["5 audit-log validation"]
    s5 --> s6["6 patch ownership cost"]
```

The framework is distilled from the **published analysis** of Ajinomoto
Group's accounting AI agent (in production since February 2026). Every
definition is machine-readable (YAML / JSON Schema), so AI agents and CI can
consume it directly.

## Who this is for

| If you are... | Start with... |
|---|---|
| **New here and want the big picture** | [docs/00 overview](docs/00_overview.md) (Japanese) — the 6 steps told through the Midori Seiki story |
| A **business decision maker** (head of accounting, CFO, compliance lead) considering AI for a process | [docs/02](docs/02_four_layer_framework.md) — score your process with `aidr check-readiness` |
| Deciding **where to start** / briefing management | [docs/01](docs/01_transition_screening.md) — the 4-type transition map and the headcount-last decision order |
| An **engineer** designing an AI agent for high-risk approvals | [schemas/audit-log.schema.json](schemas/audit-log.schema.json) + [docs/06](docs/06_audit_log_schema.md) — wire the schema into your logger |
| A **maintainer / Engineering Manager** accepting AI-generated code | [docs/11](docs/11_patch_ownership_gate.md) — gate on ownership cost, test integrity, and high-risk boundaries |
| An **operator** auditing an existing AI platform's logging | [docs/07](docs/07_audit_log_gap_check.md) — apply the 5-step method to your own SQL schema |
| An **EM / PMO** checking whether the org RUNNING the agents can stop their failures | [docs/13](docs/13_risk_architecture.md) — score detection / containment / escalation per failure scenario |
| A **consultant / proposal author** | All of `docs/` + the overlay model — clone, overlay in private, present client-specific scoring |

## Quick start (2 minutes)

No setup — pull the published image and run it. The bundled samples (the
Midori Seiki story) work out of the box:

```bash
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 --version

# The 6 main-line steps, in story order
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  screen-transition examples/task-groups/sample-task-groups.csv
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  check-readiness examples/business/sample-expense-approval.csv          # first diagnosis -> BLOCK
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  check-readiness examples/business/sample-expense-approval-after.csv    # after fixes -> PASS
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  score-delegation examples/judgments/sample-judgments.csv
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  check-task-contract examples/task-contracts/sample-green.csv
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  validate-audit-log examples/audit-log-sample.json --level extended
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  check-patch-ownership examples/patches/sample-cheap-green.csv

# Extension (optional): review accept/discard decisions after the gate
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  summarize-patch-decisions examples/patch-decisions/sample-midori-2026-07.jsonl

# Extension (optional): score the receiving organization's risk architecture
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  assess-risk-architecture examples/business/sample-risk-architecture.csv

# Extension (optional) and definition inspection
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 \
  check-overlay examples/overlays/sample-company/extra-rules.yaml
docker run --rm ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 list-definitions
```

`--version` prints the app version and the bundled overlay engine version, e.g.
`aidr 0.17.2 (overlay-scoring-skeleton 0.1.0)`.

Every command returns a deterministic exit code so you can gate CI on it:

| Command | 0 | 1 | 2 | 3 |
|---|---|---|---|---|
| check-readiness / score-delegation / check-task-contract / check-patch-ownership | ok (green) | partial (yellow) | block (red) | input error / overlay violation |
| screen-transition | success (classification, not a gate — 0 whatever the types) | — | — | missing/invalid answers, overlay violation |
| validate-audit-log | valid | invalid (schema violations) | — | input error (malformed JSON, missing file) |
| check-overlay | merges cleanly | violations (rejected) | — | malformed/duplicate-key YAML or missing file |
| summarize-patch-decisions | all decided, no RED accepted | undecided patches remain | one or more RED-accepted records (2 takes priority over 1) | input error / overlay violation |
| assess-risk-architecture | every scenario High + owners present (or pure-SE, not applicable) | some Medium, no Low | any Low, or a surface owner missing | input error / contradictory answers / overlay violation |

Reports are also available as **CSV** via `--format csv` (the 7 commands in the
table above; the leading `record_type` column distinguishes row kinds so
spreadsheets can aggregate them directly).

## Usage workflow

The commands run against *your* data. Mount the directory that holds your files
into the container. A shell function keeps the rest of this guide readable:

```bash
aidr() { docker run --rm -v "$PWD:/data" -w /data \
  ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 "$@"; }
```

Generate your input files with `aidr init` (step 1 below), then run the
commands in this order. Question texts carry both English (`text`) and
Japanese (`text_ja`) in `definitions/*.yaml`.

1. **Prepare** — generate a question-annotated CSV template via
   `aidr init --target transition|four-layer|matrix|task-contract|patch-ownership|risk-architecture --format csv > my-file.csv`
   (add `--overlay` to include your company's extra questions), open it in
   Google Sheets / Excel (UTF-8 BOM included), and fill the 回答 (answer) cells
   with yes/no (はい/いいえ also accepted). Duplicate columns to add task
   groups / judgments in the wide format. The bundled [`examples/`](examples/)
   are these templates filled with Midori Seiki's answers; YAML input still
   works (one YAML example is kept as a twin).
2. **Map where to start** — `aidr screen-transition my-task-groups.csv` sorts
   task groups into the four AI-transition types in delegation-design priority
   order: *reorganization* first (role redesign needed), *high automation*
   feeds the next steps. Groups touching rights / finances / health / regulated
   matters carry a `[HITL]` marker whatever their type. Every question must be
   answered — missing answers are an input error. See
   [docs/01](docs/01_transition_screening.md).
3. **Diagnose the process and the organization** —
   `aidr check-readiness my-business.csv` scores the four layers
   (standardization → structuring → scope → control) plus the efficacy and
   organization axes. **BLOCK is a gate, not a score**: fix the layer named by
   `First gate to fix`, then re-check. The bundled story runs first-BLOCK
   ([`sample-expense-approval.csv`](examples/business/sample-expense-approval.csv))
   then PASS
   ([`sample-expense-approval-after.csv`](examples/business/sample-expense-approval-after.csv)).
   See [docs/02](docs/02_four_layer_framework.md) / [docs/03](docs/03_organization_axis.md).
   **Applicability check**: if the delegated work involves scheduled tasks,
   device-offline execution, or a resident worker, always apply the unattended
   execution overlay
   ([docs/14](docs/14_account_resident_execution_overlay.md)) via `--overlay` —
   **a base-only PASS has not evaluated the unattended surface** (without the
   overlay the two extra axes are never merged into the definition).
   If the delegated task runs autonomously for hours, passes through context
   compaction, or can run in parallel branches, also apply the
   trajectory-oversight overlay
   ([docs/15](docs/15_trajectory_oversight_overlay.md)) —
   **a base-only PASS has not evaluated whether a stop actually stops side
   effects**.
   Once you operate multiple AI delegations through a ticket system or
   worklist — beyond per-task contracts, with per-owner or cost aggregation —
   always apply the delegation-ledger overlay
   ([docs/16](docs/16_delegation_ledger_overlay.md)) —
   **a base-only PASS has not evaluated whether the ledger can answer who
   executed, who is accountable, and at what cost**.
4. **Score the judgments** — `aidr score-delegation my-judgments.csv` places
   each judgment into GREEN (delegate), YELLOW (LLM-assist, a human decides), or
   RED (human-only). See [docs/04](docs/04_delegation_matrix.md).
5. **Check the task contract** — `aidr check-task-contract my-contract.csv`
   checks intent / boundary / evidence / scorer. An AI judge with no iRULER
   double-evaluation blocks (RED). See
   [docs/05](docs/05_task_contract_execution_rubric.md).
6. **Validate the audit log** —
   `aidr validate-audit-log my-log.json --level extended` checks who / when /
   what / why / result at J-SOX grade. See [docs/06](docs/06_audit_log_schema.md).
7. **Gate AI-generated patches** —
   `aidr check-patch-ownership my-patch.csv` checks probe size, future ownership,
   test integrity, evidence references, and never-cheap risks. High-risk patches
   require a human decision even when controlled. Add
   `--emit-decision-record <path> --team <name>` to append a pending decision
   record (JSONL) for the later retrospective. See
   [docs/11](docs/11_patch_ownership_gate.md).
8. **Review accept/discard decisions (optional)** — GREEN/YELLOW/RED is not an
   auto-merge order; a human still decides. Record that decision, then run
   `aidr summarize-patch-decisions decisions/ --period 2026-08 --team my-team`
   monthly to see the discard rate, the decided rate, and the discard-reason
   mix. See [docs/12](docs/12_patch_decision_loop.md).
9. **Score the receiving organization (optional)** —
   `aidr assess-risk-architecture my-risk-arch.csv` checks whether the org
   RUNNING the agents can detect / contain / escalate eight representative
   failure scenarios (τ = d+c+s per the framework-adequacy methodology of
   [arXiv:2607.01421](https://arxiv.org/abs/2607.01421)), gated on three
   uniquely named surface owners (contract / agent-workflow / boundary
   channel). Three caveats before selling the result: the paper's "owners
   remove Low bands" claim is a derived counterfactual, not a measurement;
   joint ownership is a RACI anti-pattern (name one decision maker per
   incident); and uniform extra governance fails — scale controls with
   autonomy (D2). See [docs/13](docs/13_risk_architecture.md).
10. **Extend (optional)** — add your own questions / thresholds via an overlay,
   validated by `aidr check-overlay <path>` and applied with `--overlay`.
   Bundled domain overlays: high-stakes professional work (IP / legal / pharma,
   [docs/08](docs/08_high_stakes_domain_overlay.md)), insourcing judgment
   responsibility ([docs/09](docs/09_insourcing_judgment_overlay.md)), agent
   authorization design ([docs/10](docs/10_agent_authorization_overlay.md)),
   account-resident / unattended execution
   ([docs/14](docs/14_account_resident_execution_overlay.md)),
   long-horizon trajectory oversight
   ([docs/15](docs/15_trajectory_oversight_overlay.md)), and
   the delegation ledger — accountability and cost
   ([docs/16](docs/16_delegation_ledger_overlay.md)):

   ```bash
   aidr check-readiness examples/business/sample-ip-agent-readiness.csv \
     --overlay examples/overlays/high-stakes-domain/four-layer.yaml
   # => L1-L4 all PASS, yet one missing prerequisite blocks at L5

   aidr score-delegation examples/judgments/sample-ip-judgments.csv \
     --overlay examples/overlays/high-stakes-domain/delegation-matrix.yaml
   # => boundary cases (2/3 on an axis) drop from green to yellow / red

   aidr check-readiness examples/business/sample-insourcing-readiness.csv \
     --overlay examples/overlays/insourcing-judgment/four-layer.yaml
   # => L1-L4 and organization all PASS, yet a missing in-house owner is REVISE/BLOCK

   aidr check-readiness examples/business/sample-agent-authz-readiness.csv \
     --overlay examples/overlays/agent-authorization/four-layer.yaml
   # => capability and consent score as two independent axes; a full capability
   #    axis does not offset a blocked consent axis

   aidr check-readiness examples/business/sample-unattended-selfhosted.csv \
     --overlay examples/overlays/account-resident-execution/four-layer.yaml
   # => unattended surface and supervision score as two independent axes; a
   #    perfect kill switch does not offset a missing approval fail-closed

   aidr check-readiness examples/business/sample-trajectory-framework-gate.csv \
     --overlay examples/overlays/trajectory-oversight/four-layer.yaml
   # => the enforcement axis is non-compensating (a single "no" is BLOCK); an
   #    untested stop is not diluted by the other answers

   aidr check-readiness examples/business/sample-ledger-scattered.csv \
     --overlay examples/overlays/delegation-ledger/four-layer.yaml
   # => accountability and cost score as two independent axes; the questions
   #    score ledger capability (record / retrieve / aggregate / detect),
   #    not the ticket-system choice
   ```

   The agent-authorization overlay's two axes are **not** a defense against
   prompt injection: when an attacker steers the LLM's judgment, both the
   authority and the consent stay legitimate and only the designation falls
   under the attacker's control.

See [`README.ja.md`](README.ja.md#使い方想定ワークフロー) for sample output of every
command in the workflow.

## What's in this repo

```
ai-delegation-readiness/
├── definitions/                 # Machine-readable canonical framework (YAML; questions carry text + text_ja)
│   ├── transition-screening.yaml #  3 axes + 4 transition types map + extension_points
│   ├── four-layer.yaml          #   4 layers + efficacy & organization axes + extension_points
│   ├── delegation-matrix.yaml   #   2 axes + region map + extension_points
│   ├── task-contract.yaml       #   4 execution-rubric elements + gate policy + extension_points
│   ├── patch-ownership.yaml     #   AI-generated patch ownership-cost acceptance gate
│   ├── patch-decision.yaml      #   Decision-record vocabulary (decision/discard_reason/reading/bands) + extension_points
│   └── risk-architecture.yaml   #   Org risk architecture (7-dim profile + scenarios + owners) + extension_points
├── schemas/
│   ├── audit-log.schema.json    # JSON Schema with $defs: minimum (A) / extended (B)
│   └── patch-decision.schema.json # JSON Schema for one decision record
├── src/adr/                     # Python diagnostic tool (shipped as a container image)
├── bin/aidr                     # CLI entry point (single command, 11 subcommands)
├── examples/                    # Samples connected by the Midori Seiki (fictional) story
│   ├── README.md                #   Canonical story profile + sample index + applied cases (Japanese)
│   ├── task-groups/             #   Step 1: screen-transition input
│   ├── business/                #   Step 2: check-readiness inputs (first BLOCK / after PASS + applied cases)
│   ├── judgments/               #   Step 3: score-delegation inputs (+ applied cases)
│   ├── task-contracts/          #   Step 4: check-task-contract inputs (green / red)
│   ├── audit-log-sample.json    #   Step 5: sample audit log (escalated case)
│   ├── patches/                 #   Step 6: check-patch-ownership inputs (green / yellow / red)
│   ├── patch-decisions/         #   Extension: summarize-patch-decisions inputs (story + feature demo)
│   ├── overlays/                #   Extension: company rules + domain overlays (applied cases)
│   └── skills/                  #   AI entry point: six Claude Code skill samples
└── docs/                        # Explanations, Japanese (reading order: the learning path in README.ja.md)
    ├── 00_overview.md           #   The big picture (read first)
    ├── 01-06, 11                #   The 6 main-line steps in detail
    ├── 07-10, 14-16             #   Applied: log-platform check / high-stakes domains / insourcing / agent authorization / unattended execution / trajectory oversight / delegation ledger
    └── 12-13                    #   Extensions: patch-decision retrospective loop / org risk architecture
```

## How to extend

The canonical foundation (`definitions/*.yaml`, `schemas/*.json`) is
**framework-consistent across companies**. Overlays may only:

- **`add`** new items to a list (existing items stay read-only)
- **`strengthen`** numeric thresholds (lowering is rejected)

Anything else (delete, replace, weaken) is a merge violation and is detected
mechanically by `aidr check-overlay`. This is what makes the framework safe to
extend without forking.

```yaml
# examples/overlays/sample-company/extra-rules.yaml (Midori Seiki's own rules)
version: 1
extends: four-layer-delegation-readiness

add:
  - id: "L4.MIDORI_Q6"
    text: Is the audit log stored in a tamper-evident store (WORM, hash chain, or signed)?
    weight: 1.0

strengthen:
  "L4": {pass: 1.0, revise: 0.8}       # was 0.6 — stricter only
```

The framework is reused in three ways:

- **AI agents**: load `definitions/*.yaml` and
  `schemas/audit-log.schema.json` into the system prompt or tool context.
  See [`examples/skills/`](examples/skills/) for six ready-to-adapt Claude
  Code skill wrappers.
- **CI pipelines**: run `docker run --rm -v "$PWD:/data" -w /data ghcr.io/suwa-sh/ai-delegation-readiness:v0.17.2 validate-audit-log <log>` on each emitted log; gate
  on exit code.
- **Internal overlays**: keep your company-specific overlay in a private repo and
  apply with `--overlay`. The framework stays a clean upstream you can pull from.

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
(`docs/02` efficacy axis).

### Source

- **Analysis article** (Japanese, the immediate source from which the framework was distilled): [「味の素の経理AIエージェントに学ぶ 承認業務をAIに委任する前提条件」](https://suwa-sh.github.io/zenn-contents/articles/ajinomoto-accounting-agent_20260621/)

### Coverage cited in the analysis article

- [Ajinomoto Financial Solutions × First Accounting press release (2026-04-24)](https://www.fastaccounting.jp/news/20260424/15929/)
- [ITmedia "76% workload reduction" coverage (2026-06-19, Japanese)](https://www.itmedia.co.jp/business/articles/2606/19/news033.html)

## License

[MIT](LICENSE)

## Security

See [SECURITY.md](SECURITY.md) for reporting vulnerabilities.
