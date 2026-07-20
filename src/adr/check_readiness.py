"""4-layer + efficacy readiness check.

Input YAML structure::

    target: <business name>
    answers:
      L1.Q1: yes
      L1.Q2: no
      ...
      efficacy.E1: yes
      ...

The CLI loads the definition (with overlays applied), scores every layer
and the efficacy axis independently, and reports PASS / REVISE / BLOCK
per layer. The first non-PASS layer is also surfaced as ``blocked_from``
in the result so the user knows where to fix first: the framework only
makes sense layered, so investing in a higher layer before the lower
one is fixed is wasted effort. Scoring is *not* short-circuited — the
report intentionally shows the state of every layer so the user can see
the full picture and the first gate at the same time.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import overlay_scoring as overlay_mod

DEFINITION_NAME = "four-layer-delegation-readiness"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "four-layer.yaml"

# group header の role: 積み上げゲート層 (gating) か、ゲートしない並列軸 (parallel) か。
ROLE_GATING = "gating"
ROLE_PARALLEL = "parallel"
_VALID_ROLES = {ROLE_GATING, ROLE_PARALLEL}
# role 未指定でも並列軸として扱う group id (後方互換: efficacy は元から並列軸)。
_IMPLICIT_PARALLEL = {"efficacy"}


def axis_role(group_id: str, header: dict) -> str:
    """Classify a group as a gating layer or a parallel axis by its ``role``.

    ``role`` unset falls back to gating, except for historically-parallel
    groups (``efficacy``). An unknown ``role`` value (e.g. a typo like
    ``paralell``) is a loud error rather than a silent demotion to gating,
    so the axis cannot be quietly inverted.
    """
    role = (header or {}).get("role")
    if role is None:
        return ROLE_PARALLEL if group_id in _IMPLICIT_PARALLEL else ROLE_GATING
    if role not in _VALID_ROLES:
        raise ValueError(
            f"group '{group_id}' has unknown role '{role}' "
            f"(allowed: {ROLE_PARALLEL}, {ROLE_GATING}, or unset)"
        )
    return role


@dataclass
class AxisResult:
    id: str
    name: str
    score: float
    verdict: str  # pass | revise | block
    yes_ids: list[str] = field(default_factory=list)
    no_ids: list[str] = field(default_factory=list)
    unknown_ids: list[str] = field(default_factory=list)


@dataclass
class CheckResult:
    target: str
    layers: list[AxisResult]
    parallel_axes: list[AxisResult]  # efficacy, organization, ... (non-gating)
    conclusion: str  # PASS | REVISE | BLOCK
    blocked_from: str | None = None


def _normalize_yes(value: Any) -> bool | None:
    """Yes/No parser tolerant of 'yes', 'no', booleans, and 1/0."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"yes", "y", "true", "1", "はい"}:
            return True
        if normalized in {"no", "n", "false", "0", "いいえ"}:
            return False
    return None


def _score_axis(
    axis_id: str,
    axis_name: str,
    questions: list[dict],
    header: dict,
    answers: dict[str, Any],
) -> AxisResult:
    yes_ids: list[str] = []
    no_ids: list[str] = []
    unknown_ids: list[str] = []
    weighted_yes = 0.0
    weighted_total = 0.0
    for q in questions:
        qid = q["id"]
        weight = float(q.get("weight", 1.0))
        weighted_total += weight
        ans = _normalize_yes(answers.get(qid))
        if ans is True:
            yes_ids.append(qid)
            weighted_yes += weight
        elif ans is False:
            no_ids.append(qid)
        else:
            unknown_ids.append(qid)
    score = (weighted_yes / weighted_total) if weighted_total else 0.0
    pass_t = float(header.get("pass", 1.0))
    revise_t = float(header.get("revise", 0.5))
    if score >= pass_t:
        verdict = "pass"
    elif score >= revise_t:
        verdict = "revise"
    else:
        verdict = "block"
    return AxisResult(
        id=axis_id,
        name=axis_name,
        score=score,
        verdict=verdict,
        yes_ids=yes_ids,
        no_ids=no_ids,
        unknown_ids=unknown_ids,
    )


def check(
    target_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> CheckResult:
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

    from . import io_input

    target, input_format, row_ids = io_input.load_input(target_path, "four-layer")
    answers = target.get("answers", {}) or {}
    if input_format == "csv":
        # CSV は Excel 経由の typo が起きやすいので、質問行の id(回答が空の行も
        # 含む)を定義と照合する(YAML は後方互換のため従来どおり未知キーを無視する)。
        known = io_input.collect_question_ids(defn, non_question_groups=set())
        io_input.validate_known_ids(row_ids, known, Path(target_path).name)

    # group を role で振り分ける: ゲート層 (L1..L4) と 並列軸 (efficacy, organization, ...)。
    # source order を保つ (group_items() のキー順)。leaf 0 個の並列軸は overlay 前提の
    # 未評価軸として採点対象から外す (誤 BLOCK を防ぐ)。ゲート層は元から leaf を持つ。
    groups = overlay_mod.group_items(defn)
    layer_results: list[AxisResult] = []
    parallel_results: list[AxisResult] = []
    for group_id, group in groups.items():
        header = group["header"] or {}
        role = axis_role(group_id, header)
        leaves = group["leaves"]
        if role == ROLE_PARALLEL and not leaves:
            continue  # 未評価の並列軸 (空) はスキップ
        axis = _score_axis(
            axis_id=group_id,
            axis_name=header.get("name_ja") or header.get("name"),
            questions=leaves,
            header=header,
            answers=answers,
        )
        if role == ROLE_PARALLEL:
            parallel_results.append(axis)
        else:
            layer_results.append(axis)

    # ゲート層のみが blocked_from を作る (並列軸は上層をゲートしない)。
    blocked_from: str | None = None
    for layer in layer_results:
        if blocked_from is None and layer.verdict != "pass":
            blocked_from = layer.id

    overall_axes = layer_results + parallel_results
    verdicts = {axis.verdict for axis in overall_axes}
    if verdicts == {"pass"}:
        conclusion = "PASS"
    elif "block" in verdicts:
        conclusion = "BLOCK"
    else:
        conclusion = "REVISE"

    return CheckResult(
        target=target.get("target", str(target_path)),
        layers=layer_results,
        parallel_axes=parallel_results,
        conclusion=conclusion,
        blocked_from=blocked_from,
    )


class OverlayError(Exception):
    def __init__(self, violations):
        self.violations = violations
        msg = "; ".join(f"{v.path}: {v.message}" for v in violations)
        super().__init__(f"overlay violations: {msg}")


def render_text(result: CheckResult) -> str:
    lines = [f"Target: {result.target}", ""]
    for layer in result.layers:
        bar = _verdict_marker(layer.verdict)
        score_pct = f"{int(layer.score * 100)}%"
        lines.append(f"{bar} {layer.id} {layer.name}: {layer.verdict.upper()} ({score_pct})")
        if layer.no_ids:
            lines.append(f"    no: {', '.join(layer.no_ids)}")
        if layer.unknown_ids:
            lines.append(f"    unknown: {', '.join(layer.unknown_ids)}")
        if result.blocked_from == layer.id and layer.verdict != "pass":
            lines.append("    -> upper layers are gated by this verdict")
    for axis in result.parallel_axes:
        bar = _verdict_marker(axis.verdict)
        lines.append(
            f"{bar} {axis.id} {axis.name}: {axis.verdict.upper()} "
            f"({int(axis.score * 100)}%)"
        )
        if axis.no_ids:
            lines.append(f"    no: {', '.join(axis.no_ids)}")
        if axis.unknown_ids:
            lines.append(f"    unknown: {', '.join(axis.unknown_ids)}")
    lines.append("")
    lines.append(f"Conclusion: {result.conclusion}")
    if result.conclusion != "PASS" and result.blocked_from:
        lines.append(f"  First gate to fix: layer {result.blocked_from}")
    return "\n".join(lines)


def _verdict_marker(verdict: str) -> str:
    return {"pass": "[OK]", "revise": "[..]", "block": "[NG]"}.get(verdict, "[??]")


def render_json(result: CheckResult) -> str:
    payload = {
        "target": result.target,
        "conclusion": result.conclusion,
        "blocked_from": result.blocked_from,
        "layers": [_axis_to_dict(layer) for layer in result.layers],
        "parallel_axes": [_axis_to_dict(a) for a in result.parallel_axes],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _axis_to_dict(axis: AxisResult) -> dict:
    return {
        "id": axis.id,
        "name": axis.name,
        "verdict": axis.verdict,
        "score": axis.score,
        "yes": axis.yes_ids,
        "no": axis.no_ids,
        "unknown": axis.unknown_ids,
    }


def render_csv_rows(result: CheckResult) -> list[list[str]]:
    """レポートの CSV 行列。

    先頭の record_type 列で行の種類を、target 列で診断対象を機械判別できる —
    複数対象のレポートを連結しても、明細行(axis)単体で対象を識別できる。
    """
    from .io_input import sanitize_cell

    target = sanitize_cell(result.target)
    rows = [["record_type", "target", "id", "name", "role", "verdict", "score_pct", "no", "unknown"]]
    for role, axes in (("layer", result.layers), ("parallel", result.parallel_axes)):
        for a in axes:
            rows.append([
                "axis", target, a.id, a.name, role, a.verdict, str(int(a.score * 100)),
                "; ".join(a.no_ids), "; ".join(a.unknown_ids),
            ])
    rows.append(["summary", target, "conclusion", result.conclusion, "", "", "", "", ""])
    if result.blocked_from:
        rows.append(["summary", target, "first_gate_to_fix", result.blocked_from, "", "", "", "", ""])
    return rows


def exit_code_for(result: CheckResult) -> int:
    return {"PASS": 0, "REVISE": 1, "BLOCK": 2}[result.conclusion]
