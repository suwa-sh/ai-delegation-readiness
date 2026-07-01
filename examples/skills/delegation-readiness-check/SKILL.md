---
name: delegation-readiness-check
description: Walk a user through the 4-layer readiness check for AI delegation. Loads definitions/four-layer.yaml, asks the questions interactively, and reports PASS/REVISE/BLOCK per layer with the first gate to fix. Use when the user wants to evaluate whether a specific business process is ready to delegate to an AI agent, or asks to "do a readiness check" or "score this process."
---

# delegation-readiness-check

Interactively score a business process against the 4-layer + efficacy
framework from this repository. The skill is a thin wrapper around the
`aidr check-readiness` CLI: it gathers answers via dialogue, writes a
business YAML, runs the CLI in JSON mode, and translates the verdict
back into a readable summary plus the first gate to fix.

## When to use this skill

- The user names a business process and wants to know whether it can be
  delegated to an AI agent (e.g. "expense approval", "vendor onboarding")
- The user asks to run a readiness check / 4-layer check / governance gate
- The user wants to evaluate a process against an overlay (their own
  company's strengthened rules)

## What this skill needs from the user

- The name of the target business process (free text)
- Optionally: a path to one or more overlay YAML files to apply

## Workflow

1. Ask the user for the target process name. Confirm scope (single
   approval type vs end-to-end process) if it is ambiguous.

2. Read `definitions/four-layer.yaml` to retrieve the questions. Do not
   hard-code the questions in this skill — always read from the
   definition file so overlays and version bumps stay in sync.

3. Pose each layer's questions in order. Ask one layer at a time and
   record `yes` / `no` / `unknown` per question id. If the user is
   unsure, mark `unknown` (the CLI treats unknown as no for scoring but
   surfaces it separately in the report).

4. Pose the efficacy axis questions after L4.

5. Write the collected answers to a temporary YAML at
   `/tmp/aidr-readiness-<timestamp>.yaml` with the shape:

   ```yaml
   target: <process name>
   answers:
     L1.Q1: yes
     L1.Q2: no
     ...
   ```

6. Run `bin/aidr check-readiness <tmp.yaml> --format json` (add
   `--overlay <path>` for each overlay the user provided). Capture
   stdout and the exit code.

7. Translate the JSON output for the user. Lead with the conclusion
   (PASS / REVISE / BLOCK), then for each layer with verdict != pass:
   - which questions failed
   - whether the layer is the first gate (`blocked_from`)
   - a one-sentence next action drawn from the layer's `purpose` field

8. If the conclusion is BLOCK or REVISE, recommend the next concrete
   step: "fix layer L<N> first, then re-run the check." Do not
   recommend delegating to AI yet.

## Output etiquette

- Keep the per-question dialogue tight. Group questions by layer so the
  user can answer in a short batch rather than one-by-one.
- Show the structured verdict before the narrative explanation.
- Quote the source case-evidence (Ajinomoto example) only when the user
  asks for context. The framework is the artifact, not the case study.

## Failure modes to handle

- If `bin/aidr` is not on PATH, fall back to
  `python -m adr.cli check-readiness ...` with `PYTHONPATH` set to the
  repo's `src/` directory.
- If the overlay fails `check-overlay`, surface the violation and stop
  rather than scoring with a half-applied overlay.
- If the user answers in a free-form way ("kind of", "depends"), prompt
  for a binary yes/no and capture the nuance in a note for the report.
