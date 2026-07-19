---
name: transition-screening
description: Screen a user's task groups into the four AI-transition types (growth / high automation / reorganization / minimal change) before any delegation scoring. Loads definitions/transition-screening.yaml, asks the 3 axes' questions per task group, runs `aidr screen-transition`, and reports the delegation-design priority order with HITL flags. Use when the user asks "where should we start with AI?", "which tasks to delegate first?", or wants a workforce-transition map before headcount talk.
---

# transition-screening

Interactively classify a set of task groups into the four AI-transition
types from this repository. The skill is a thin wrapper around the
`aidr screen-transition` CLI: it gathers answers via dialogue, writes a
task-groups YAML, runs the CLI in JSON mode, and translates the result
into a "where to start delegation design" map — with the decision order
that puts headcount last.

## When to use this skill

- The user wants to decide **which task groups to tackle first** with AI
  (before scoring individual judgments with `score-delegation`)
- The user asks for a workforce-transition view ("which of our jobs
  grow / automate / reorganize?") grounded in a machine-readable lens
- A client proposal needs the "4-type map -> delegation design ->
  headcount last" decision order with sources and confidence labels

## What this skill needs from the user

- A list of task groups (free text; 3-10 groups works best). A task
  group is a coherent bundle of tasks (e.g. "accounting entry checks",
  "customer support chat"), not a job title.
- Optionally: a path to an overlay YAML adding company-specific questions

## Workflow

1. Ask the user for the task groups. Nudge them toward task bundles, not
   occupation names (the screening scores what the work is, not who does
   it today).

2. Read `definitions/transition-screening.yaml` to retrieve the three
   axes' questions. Do not hard-code the questions — always read from
   the definition file so overlays and version bumps stay in sync.

3. For each task group, pose the questions one axis at a time
   (technical_exposure E1-E3, human_necessity H1-H3, demand_elasticity
   D1-D3). **Every question must be answered** — the CLI rejects missing
   answers (fail-closed), so do not skip any. If the user is unsure,
   discuss until they can commit to yes/no; do not guess for them.

4. Write the answers to a temporary YAML at
   `/tmp/aidr-screening-<timestamp>.yaml` with the shape shown in
   `examples/task-groups/sample-task-groups.yaml`:

   ```yaml
   task_groups:
     - id: <slug>
       description: <task group name>
       answers:
         technical_exposure.E1: yes
         ...
   ```

5. Run `bin/aidr screen-transition <tmp.yaml> --format json` (add
   `--overlay <path>` if provided). Capture stdout.

6. Translate the JSON for the user, in the delegation-priority order the
   CLI already returns:
   - **reorganization** groups first: flag them as the design-heavy zone
     (humans stay, headcount demand may shrink; role redesign needed)
   - **high_automation** groups: recommend the next step —
     `aidr score-delegation` on their concrete judgments
   - groups with `human_control_required: true`: state explicitly that a
     human keeps the final decision (rights / finances / health /
     regulated matters), whatever the type
   - close with the decision order from the `action` texts: decompose ->
     sort -> redefine roles -> reskill -> headcount **last**

7. When the user asks for sources, quote the `case_evidence` entries from
   the JSON output **with their confidence labels**. Never present a
   `claim_needs_verification` figure (e.g. the WEF redeploy split) as
   established fact in client-facing material.

## Output etiquette

- Lead with the priority-ordered map, then the narrative.
- Keep the "planning map, not a job-loss prediction" framing in the
  summary — the screening result is where to *start designing*, not who
  to cut.
- Borderline classifications (an axis at exactly its threshold) deserve
  a one-line caveat inviting a human re-check.

## Failure modes to handle

- If `bin/aidr` is not on PATH, fall back to
  `python -m adr.cli screen-transition ...` with `PYTHONPATH` set to the
  repo's `src/` directory.
- If the CLI exits 3 with missing answer ids, return to step 3 for those
  questions rather than filling in defaults.
- If the overlay fails `check-overlay`, surface the violation and stop.
