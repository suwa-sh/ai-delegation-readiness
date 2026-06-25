---
name: audit-log-validate
description: Validate an AI delegation audit log JSON against schemas/audit-log.schema.json. Picks the minimum (article-aligned) or extended (J-SOX-grade) schema level per the user's intent, runs the aidr validator, and reports violations by JSON path. Use when the user wants to check whether an audit log meets the schema, or asks to "validate the log" or "check this audit log."
---

# audit-log-validate

Validate an audit log JSON file against the repository's audit log
schema, then explain the violations in human terms. Thin wrapper around
`aidr validate-audit-log`.

## When to use this skill

- The user supplies an audit log JSON file (or its contents) and asks
  whether it conforms to the schema
- The user is designing an audit log writer and wants quick feedback on
  whether their output passes the minimum or extended schema
- The user asks for J-SOX-grade validation (-> use `extended`)

## What this skill needs from the user

- The path to (or contents of) the audit log JSON
- The intended schema level: `minimum` (default, article-aligned) or
  `extended` (J-SOX-grade: rule version pinned, discrete decision enum,
  escalated_to required when escalated)

## Workflow

1. Confirm with the user which schema level they want to validate
   against. If they mention J-SOX, audit, compliance, or "production",
   default to `extended` and tell them why.

2. If the user pasted JSON content instead of a path, write it to
   `/tmp/aidr-log-<timestamp>.json`.

3. Run `bin/aidr validate-audit-log <path> --level <level> --format json`.
   Capture stdout and the exit code.

4. If exit code is 0, report a one-line success with the level used and
   suggest the next action (e.g. "ready for ingestion" or "extend to
   `extended` next").

5. If there are violations, group them by top-level field (who / when /
   what / why / result) and translate the JSON Schema messages into
   plain explanations:
   - "result.decision must be one of approved/rejected/escalated" ->
     "the decision value must be a discrete enum; remove free-form text"
   - "why.rule_refs[0]/version required" -> "extended schema requires
     pinning the rule version (date or tag) at decision time"
   - "result/escalated_to required" -> "when decision is `escalated`, the
     escalated_to field (a human principal) is required"

6. End with the next concrete action: "fix these N fields, re-run
   `aidr validate-audit-log` to confirm."

## Output etiquette

- Lead with the verdict (`[OK]` or `[NG] N violations`).
- Show the JSON paths verbatim so the user can grep their log.
- Do not paraphrase the audit log content back to the user; assume they
  can read their own JSON.

## Failure modes to handle

- File not found: tell the user the path, do not guess.
- JSON syntax error: surface the parser error and stop. Do not try to
  guess what the user meant.
- The wrong schema level was requested ("minimum" for a log that has
  free-form decision text): the validation will pass, but warn the user
  that the schema is intentionally lax at minimum level.
