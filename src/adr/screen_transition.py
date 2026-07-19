"""Screen task groups into the four AI-transition types (pre-delegation).

Input YAML structure::

    task_groups:
      - id: accounting_entry_check
        description: Accounting entry check tasks
        answers:
          technical_exposure.E1: yes
          technical_exposure.E2: yes
          technical_exposure.E3: yes
          human_necessity.H1: yes
          human_necessity.H2: no
          human_necessity.H3: no
          demand_elasticity.D1: no
          demand_elasticity.D2: no
          demand_elasticity.D3: no

The output lists each task group with its three axis levels (high or low),
the transition type (growth / high_automation / reorganization /
minimal_change), its delegation-design priority, and the recommended
decision order (headcount last). Groups are rendered in priority order so
the output reads as a "where to start delegation design" map.

Contracts that differ from ``score_delegation``:

- **Answers are mandatory (fail-closed).** ``score_delegation`` treats a
  missing answer as "no"; here a missing answer for any question is an
  input error (exit 3) listing the missing ids. Rationale: an unanswered
  ``human_necessity`` question would silently score the axis low and tip
  the group into ``high_automation`` (the humans-not-needed side) — a
  fail-open misclassification for a planning map.
- **Exit code is always 0 on success.** Screening is a classification, not
  a pass/fail gate, so no type maps to a non-zero code. Only overlay or
  input errors exit 3. (``score-delegation`` exits 0/1/2 by region because
  its regions are a delegation verdict.)
- **``human_control_required`` is independent of the type.** Questions
  carrying ``flag: human_control`` (H1, the default HITL domains: rights /
  finances / health / regulation) raise the flag on a yes answer whatever
  type the group lands in, so a ``growth`` result cannot swallow the HITL
  requirement.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import overlay_scoring as overlay_mod
from .check_readiness import OverlayError, _normalize_yes
from .score_delegation import AxisScore, _resolve_region

DEFINITION_NAME = "transition-screening"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "transition-screening.yaml"

# axes / types / examples 以外の追加 group が将来生えても axis として扱えるよう、
# 予約された非 axis group id はここに列挙する (types は評価用ルックアップ、examples はデータ)。
_NON_AXIS_GROUPS = {"types", "examples"}

_HUMAN_CONTROL_FLAG = "human_control"


class InputError(Exception):
    """Raised when the task-groups input violates the fail-closed contract."""


@dataclass
class TaskGroupResult:
    id: str
    description: str
    axes: dict[str, AxisScore]
    type: str  # growth | high_automation | reorganization | minimal_change
    type_name_ja: str
    delegation_priority: int
    human_control_required: bool
    human_control_yes_ids: list[str] = field(default_factory=list)
    action: str = ""


@dataclass
class ScreenResult:
    task_groups: list[TaskGroupResult]
    case_evidence: list[dict] = field(default_factory=list)

    # Screening is a classification, not a gate: success is always exit 0.
    exit_code: int = 0


def _score_axis_strict(
    axis_id: str, questions: list[dict], header: dict, answers: dict
) -> tuple[AxisScore, list[str]]:
    """Score one axis; return the score and any missing question ids."""
    yes_ids: list[str] = []
    no_ids: list[str] = []
    missing: list[str] = []
    for q in questions:
        qid = q["id"]
        if qid not in answers:
            missing.append(qid)
            continue
        ans = _normalize_yes(answers.get(qid))
        if ans is True:
            yes_ids.append(qid)
        else:
            no_ids.append(qid)
    threshold = int(header.get("threshold", len(questions)))
    score = len(yes_ids)
    level = "high" if score >= threshold else "low"
    return (
        AxisScore(
            axis_id=axis_id,
            score=score,
            threshold=threshold,
            level=level,
            yes_ids=yes_ids,
            no_ids=no_ids,
        ),
        missing,
    )


def _flagged_question_ids(axis_groups: dict, flag: str) -> set[str]:
    return {
        leaf["id"]
        for group in axis_groups.values()
        for leaf in group["leaves"]
        if leaf.get("flag") == flag
    }


def screen(
    task_groups_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> ScreenResult:
    overlay_paths = overlay_paths or []
    definition_path = definition_path or DEFAULT_DEFINITION
    base = overlay_mod.load_yaml(definition_path)
    if overlay_paths:
        result = overlay_mod.apply_overlays(base, overlay_paths)
        if not result.ok:
            raise OverlayError(result.violations)
        defn = result.merged
    else:
        defn = base

    sep = overlay_mod.separator_of(defn)
    groups = overlay_mod.group_items(defn)
    axis_groups = {gid: g for gid, g in groups.items() if gid not in _NON_AXIS_GROUPS}
    type_leaves = groups["types"]["leaves"]
    type_evidence = (groups["types"]["header"] or {}).get("case_evidence", []) or []
    human_control_ids = _flagged_question_ids(axis_groups, _HUMAN_CONTROL_FLAG)

    input_data = overlay_mod.load_yaml(task_groups_path)
    if not isinstance(input_data, dict):
        raise InputError("input must be a YAML mapping with a 'task_groups' list")
    groups_in = input_data.get("task_groups", []) or []
    if not isinstance(groups_in, list):
        raise InputError("'task_groups' must be a list")

    results: list[TaskGroupResult] = []
    for g in groups_in:
        gid = g.get("id") or g.get("description", "<unnamed>")
        desc = g.get("description") or gid
        answers = g.get("answers", {}) or {}

        axis_scores: dict[str, AxisScore] = {}
        missing_all: list[str] = []
        for aid, group in axis_groups.items():
            score, missing = _score_axis_strict(aid, group["leaves"], group["header"], answers)
            axis_scores[aid] = score
            missing_all.extend(missing)
        # Fail-closed: every question must be answered. A silent "missing =
        # no" would tip human_necessity low and misclassify toward
        # high_automation (see module docstring).
        if missing_all:
            raise InputError(
                f"task group '{gid}' is missing answers for: {', '.join(missing_all)}"
            )

        axis_levels = {aid: s.level for aid, s in axis_scores.items()}
        type_leaf = _resolve_region(type_leaves, axis_levels, sep)
        hc_yes = sorted(
            qid for s in axis_scores.values() for qid in s.yes_ids if qid in human_control_ids
        )
        results.append(
            TaskGroupResult(
                id=gid,
                description=desc,
                axes=axis_scores,
                type=type_leaf["id"],
                type_name_ja=type_leaf.get("name_ja", type_leaf["id"]),
                delegation_priority=int(type_leaf.get("delegation_priority", 99)),
                human_control_required=bool(hc_yes),
                human_control_yes_ids=hc_yes,
                action=type_leaf.get("action", "").strip(),
            )
        )
    # Render in delegation-design priority order (stable for equal priority).
    results.sort(key=lambda r: r.delegation_priority)
    return ScreenResult(task_groups=results, case_evidence=type_evidence)


_TYPE_MARKERS = {
    "reorganization": "[REORG ]",
    "high_automation": "[AUTO  ]",
    "growth": "[GROWTH]",
    "minimal_change": "[STABLE]",
}


def render_text(result: ScreenResult) -> str:
    if not result.task_groups:
        return "No task groups screened."
    lines = []
    for r in result.task_groups:
        marker = _TYPE_MARKERS.get(r.type, "[?     ]")
        hitl = " [HITL]" if r.human_control_required else ""
        axis_summary = ", ".join(
            f"{aid}={s.level}({s.score}/{len(s.yes_ids) + len(s.no_ids)})"
            for aid, s in r.axes.items()
        )
        lines.append(
            f"{marker} priority {r.delegation_priority}: {r.id}: "
            f"{r.type.upper()}{hitl}  ({axis_summary})"
        )
        lines.append(f"    {r.description}")
        if r.human_control_required:
            lines.append(
                "    HITL: human decision required by the default fixed domains "
                f"(rights/finances/health/regulation): {', '.join(r.human_control_yes_ids)}"
            )
        action_lines = r.action.splitlines() or [""]
        lines.append(f"    action: {action_lines[0]}")
        lines.extend(f"            {al}" for al in action_lines[1:])
    lines.append("")
    lines.append(
        "Note: a planning map, not a job-loss prediction (simplified screening "
        "derived from OpenAI's EU AI Jobs Transition Framework). Decide headcount last."
    )
    return "\n".join(lines)


def render_json(result: ScreenResult) -> str:
    payload = {
        "task_groups": [
            {
                "id": r.id,
                "description": r.description,
                "type": r.type,
                "type_name_ja": r.type_name_ja,
                "delegation_priority": r.delegation_priority,
                "human_control_required": r.human_control_required,
                "human_control_yes_ids": r.human_control_yes_ids,
                "axes": {
                    aid: {
                        "score": s.score,
                        "threshold": s.threshold,
                        "level": s.level,
                        "yes": s.yes_ids,
                        "no": s.no_ids,
                    }
                    for aid, s in r.axes.items()
                },
                "action": r.action,
            }
            for r in result.task_groups
        ],
        # Source notes (incl. the EU=12/14/27/47 vs US=18/24/12/46 mix-up
        # warning) with confidence labels, for client-facing traceability.
        "case_evidence": result.case_evidence,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
