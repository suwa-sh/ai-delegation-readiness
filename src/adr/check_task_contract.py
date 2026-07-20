"""Score a delegated task's execution contract against the 4-element rubric.

This is the phase *after* readiness (check-readiness / score-delegation):
readiness decides whether a business may be delegated at all; this rubric
checks how a single task is handed over and scored, via four elements —
intent / boundary / evidence / scorer.

Input YAML structure::

    task: Expense approval delegated to the accounting agent
    answers:
      intent.I1: yes
      intent.I2: yes
      intent.I3: yes
      boundary.B1: yes
      boundary.B2: yes
      boundary.B3: no
      evidence.E1: yes
      evidence.E2: yes
      evidence.E3: yes
      scorer.S1: yes
      scorer.S2: yes
      scorer.type: ai_judge          # required: human | ai_judge | two_stage
      scorer.iruler_double_eval: no  # -> red (AI judge without double-eval)

Each element is scored over its ``kind: question`` leaves only (the ``scorer``
group also carries ``kind: data`` leaves the gate reads directly). An element
is *present* when its yes-count reaches the group threshold, *partial* when
some but not enough are yes, *absent* when none are yes.

The region (green / yellow / red) and its exit code are resolved from the
definition's ``gates`` leaves: each declares a ``when`` list of condition
tokens (evaluated top-down, first match wins) and an ``exit_code``. The
condition tokens map 1:1 to :data:`CONDITION_EVALUATORS`; ``test_check_task_contract``
holds a conformance test that keeps the two in sync.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import overlay_scoring as overlay_mod

from .check_readiness import OverlayError, _normalize_yes

DEFINITION_NAME = "task-contract"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "task-contract.yaml"

_SCORER_TYPE_ID = "scorer.type"
_IRULER_ID = "scorer.iruler_double_eval"
_FALLBACK_SCORER_ENUM = ("human", "ai_judge", "two_stage")


class InputError(Exception):
    """The task-contract input (or the definition's gate policy) is malformed.

    Surfaced by the CLI as exit code 3 (input error), matching how
    ``OverlayError`` is handled: a bad ``scorer.type`` must not silently
    bypass the iRULER gate, so it is a loud error rather than a default.
    """


@dataclass
class ElementScore:
    id: str
    name: str
    score: int
    threshold: int
    level: str  # present | partial | absent
    yes_ids: list[str] = field(default_factory=list)
    no_ids: list[str] = field(default_factory=list)


@dataclass
class ContractResult:
    task: str
    elements: list[ElementScore]
    scorer_type: str
    iruler_double_eval: bool | None
    region: str  # green | yellow | red (leaf slug)
    region_name: str
    rationale: str
    exit_code: int
    active_conditions: list[str]


# --- gate condition evaluators (token -> predicate over the scored context) ---
# Each token here must appear in some gates.*.when in task-contract.yaml, and
# every non-'otherwise' token used there must be a key here. The conformance
# test in test_check_task_contract enforces both directions.

def _cond_any_element_absent(ctx: dict) -> bool:
    return any(e.level == "absent" for e in ctx["elements"])


def _cond_any_element_partial(ctx: dict) -> bool:
    return any(e.level == "partial" for e in ctx["elements"])


def _cond_ai_judge_without_iruler(ctx: dict) -> bool:
    # The safety gate: an AI judge scoring against a single rubric with no
    # second-order (iRULER) check. two_stage carries a human second stage, so
    # it is not caught here. Missing/unparseable iruler counts as "not in place".
    return ctx["scorer_type"] == "ai_judge" and ctx["iruler"] is not True


CONDITION_EVALUATORS: dict[str, Callable[[dict], bool]] = {
    "any_element_absent": _cond_any_element_absent,
    "any_element_partial": _cond_any_element_partial,
    "ai_judge_without_iruler": _cond_ai_judge_without_iruler,
}
_OTHERWISE = "otherwise"


def _iruler_state(raw: Any) -> bool | None:
    """Strict yes-parser for the iRULER safety gate — fails closed.

    The shared ``_normalize_yes`` treats any truthy number as yes (``bool(2)``
    is True), which would let ``iruler_double_eval: 2`` silently open the safety
    gate. Here only an explicit yes counts; anything else (no, a stray number,
    "maybe") means the double-eval is *not* in place, so the gate fires. Returns
    None when unset (also "not in place" for the gate, but shown as unset).
    """
    if raw is None:
        return None
    if raw is True:
        return True
    if isinstance(raw, str) and raw.strip().lower() in {"yes", "y", "true", "はい"}:
        return True
    return False


def _question_leaves(group: dict) -> list[dict]:
    # Default a missing ``kind`` to "question" so an overlay that adds a leaf
    # without tagging it (overlays only add to the four element groups) is still
    # scored, matching list_definitions' count. Data leaves (scorer.type,
    # scorer.iruler_double_eval) and gates carry an explicit ``kind`` and are
    # excluded.
    return [leaf for leaf in group["leaves"] if leaf.get("kind", "question") == "question"]


def _score_element(group_id: str, group: dict, answers: dict[str, Any]) -> ElementScore:
    header = group["header"] or {}
    questions = _question_leaves(group)
    yes_ids: list[str] = []
    no_ids: list[str] = []
    for q in questions:
        ans = _normalize_yes(answers.get(q["id"]))
        if ans is True:
            yes_ids.append(q["id"])
        elif ans is False:
            no_ids.append(q["id"])
    threshold = int(header.get("threshold", len(questions)))
    score = len(yes_ids)
    if not questions:
        # A required element with no questions is undeclared, not vacuously
        # present — otherwise a future 0-question group would fail open.
        level = "absent"
    elif score >= threshold:
        level = "present"
    elif score > 0:
        level = "partial"
    else:
        level = "absent"
    return ElementScore(
        id=group_id,
        name=header.get("name_ja") or header.get("name") or group_id,
        score=score,
        threshold=threshold,
        level=level,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )


def _scorer_type_enum(scorer_group: dict) -> tuple[str, ...]:
    for leaf in scorer_group.get("leaves", []):
        if leaf.get("id") == _SCORER_TYPE_ID and isinstance(leaf.get("enum"), list):
            return tuple(str(v) for v in leaf["enum"])
    return _FALLBACK_SCORER_ENUM


def _read_scorer_type(answers: dict[str, Any], allowed: tuple[str, ...]) -> str:
    raw = answers.get(_SCORER_TYPE_ID)
    if raw is None:
        raise InputError(
            f"'{_SCORER_TYPE_ID}' is required (one of: {', '.join(allowed)})"
        )
    value = str(raw).strip().lower()
    if value not in allowed:
        raise InputError(
            f"'{_SCORER_TYPE_ID}' must be one of {', '.join(allowed)}, got '{raw}'"
        )
    return value


def _resolve_region(gate_leaves: list[dict], ctx: dict, sep: str) -> dict:
    """Walk gate leaves in source order; first whose ``when`` matches wins.

    A leaf matches if any of its ``when`` tokens is active, or the token is
    ``otherwise``. Returns the leaf with its id reduced to the local slug
    (``red``/``yellow``/``green``).
    """
    for leaf in gate_leaves:
        tokens = leaf.get("when", [])
        if isinstance(tokens, str):
            tokens = [tokens]
        for tok in tokens:
            if tok == _OTHERWISE:
                return {**leaf, "id": leaf["id"].split(sep, 1)[1]}
            evaluator = CONDITION_EVALUATORS.get(tok)
            if evaluator is None:
                raise InputError(
                    f"gate leaf '{leaf['id']}' references unknown condition '{tok}'"
                )
            if evaluator(ctx):
                return {**leaf, "id": leaf["id"].split(sep, 1)[1]}
    raise InputError("no gate region matched (gates must include an 'otherwise' fallback)")


def score(
    contract_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> ContractResult:
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

    # Element groups are every non-lookup/data group. Presence-question count is
    # NOT a filter here: a required element with zero questions must still be
    # scored (as absent), so a future 0-question group fails closed, not open.
    element_groups = {
        gid: g
        for gid, g in groups.items()
        if (g["header"] or {}).get("kind") not in ("lookup", "data")
    }
    if "gates" not in groups:
        raise InputError("definition is missing the 'gates' group")

    from . import io_input

    input_data, input_format, row_ids = io_input.load_input(contract_path, "task-contract")
    if not isinstance(input_data, dict):
        raise InputError("task contract must be a mapping with 'task' and 'answers'")
    if input_format == "csv":
        known = io_input.collect_question_ids(
            defn, non_question_groups={"gates", "examples"}
        )
        io_input.validate_known_ids(row_ids, known, Path(contract_path).name)
    task = input_data.get("task") or str(contract_path)
    answers = input_data.get("answers", {}) or {}
    if not isinstance(answers, dict):
        raise InputError("'answers' must be a mapping of question id -> yes/no")

    elements = [
        _score_element(gid, g, answers) for gid, g in element_groups.items()
    ]

    scorer_group = groups.get("scorer", {})
    allowed = _scorer_type_enum(scorer_group)
    scorer_type = _read_scorer_type(answers, allowed)
    iruler = _iruler_state(answers.get(_IRULER_ID))

    ctx = {"elements": elements, "scorer_type": scorer_type, "iruler": iruler}
    region_leaf = _resolve_region(groups["gates"]["leaves"], ctx, sep)
    active = [tok for tok, ev in CONDITION_EVALUATORS.items() if ev(ctx)]

    return ContractResult(
        task=task,
        elements=elements,
        scorer_type=scorer_type,
        iruler_double_eval=iruler,
        region=region_leaf["id"],
        region_name=region_leaf.get("name_ja") or region_leaf.get("name") or region_leaf["id"],
        rationale=(region_leaf.get("action") or "").strip(),
        exit_code=int(region_leaf["exit_code"]),
        active_conditions=active,
    )


def render_text(result: ContractResult) -> str:
    lines = [f"Task: {result.task}", ""]
    for e in result.elements:
        marker = _level_marker(e.level)
        lines.append(f"{marker} {e.id} {e.name}: {e.level.upper()} ({e.score}/{e.threshold})")
        if e.no_ids:
            lines.append(f"    no: {', '.join(e.no_ids)}")
    lines.append("")
    lines.append(
        f"scorer: {result.scorer_type} "
        f"(iRULER double-eval: {_iruler_label(result.iruler_double_eval)})"
    )
    lines.append("")
    lines.append(f"Region: {result.region.upper()} — {result.region_name}")
    lines.append(f"  {result.rationale}")
    return "\n".join(lines)


def render_json(result: ContractResult) -> str:
    payload = {
        "task": result.task,
        "region": result.region,
        "region_name": result.region_name,
        "exit_code": result.exit_code,
        "scorer_type": result.scorer_type,
        "iruler_double_eval": result.iruler_double_eval,
        "active_conditions": result.active_conditions,
        "elements": [
            {
                "id": e.id,
                "name": e.name,
                "level": e.level,
                "score": e.score,
                "threshold": e.threshold,
                "yes": e.yes_ids,
                "no": e.no_ids,
            }
            for e in result.elements
        ],
        "action": result.rationale,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _level_marker(level: str) -> str:
    return {"present": "[GREEN ]", "partial": "[YELLOW]", "absent": "[RED   ]"}.get(level, "[?     ]")


def _iruler_label(value: bool | None) -> str:
    """Render the tri-state iRULER flag. Unanswered stays distinct from 'no'."""
    if value is None:
        return "unset"
    return "yes" if value else "no"


def render_csv_rows(result: ContractResult) -> list[list[str]]:
    """レポートの CSV 行列。task 列を全行に持たせ、連結集計に耐える形にする。

    summary 行の notes に推奨アクション、active_conditions 行に発火した
    ゲート条件を残す — CSV だけを受け取った担当者が「要素欠落」か
    「AI 採点者の二重評価不足」かを判別して直せるように。
    """
    from .io_input import sanitize_cell

    task = sanitize_cell(result.task)
    rows = [["record_type", "task", "id", "name", "level", "score", "threshold", "no", "notes"]]
    for e in result.elements:
        rows.append([
            "element", task, e.id, e.name, e.level, str(e.score), str(e.threshold),
            "; ".join(e.no_ids), "",
        ])
    rows.append(["scorer", task, "type", result.scorer_type, "", "", "", "", ""])
    rows.append([
        "scorer", task, "iruler_double_eval",
        _iruler_label(result.iruler_double_eval), "", "", "", "", "",
    ])
    rows.append([
        "summary", task, "region", result.region_name, result.region, "", "", "",
        " ".join(result.rationale.split()),
    ])
    rows.append([
        "summary", task, "active_conditions", "; ".join(result.active_conditions),
        "", "", "", "", "",
    ])
    return rows
