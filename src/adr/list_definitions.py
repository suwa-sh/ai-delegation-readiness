"""Show what definitions and overlays are loaded for a given run.

Useful when a team layers several overlays and wants to inspect the
resulting merged definition (added questions, strengthened thresholds)
before running ``check-readiness`` or ``score-delegation``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import overlay_scoring as overlay_mod

DEFAULT_DEFINITIONS_DIR = Path(__file__).resolve().parents[2] / "definitions"


@dataclass
class LayerSummary:
    id: str
    name: str
    question_count: int
    thresholds: dict
    added_question_ids: list[str] = field(default_factory=list)
    strengthened_thresholds: dict = field(default_factory=dict)


@dataclass
class DefinitionSummary:
    name: str
    base_path: str
    overlays_applied: list[str]
    layers: list[LayerSummary] = field(default_factory=list)
    axes: list[LayerSummary] = field(default_factory=list)  # delegation-matrix scoring axes
    parallel_axes: list[LayerSummary] = field(default_factory=list)  # four-layer non-gating axes (efficacy, organization)


def summarize_four_layer(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    return _summarize(
        name="four-layer-delegation-readiness",
        default_filename="four-layer.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=False,
    )


def summarize_matrix(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    return _summarize(
        name="delegation-matrix",
        default_filename="delegation-matrix.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
    )


def summarize_task_contract(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    # The 4 execution-rubric elements (intent/boundary/evidence/scorer) are
    # scored like matrix axes (absolute threshold over question leaves); gates
    # and examples are lookup groups and are excluded via _NON_AXIS_GROUPS.
    return _summarize(
        name="task-contract",
        default_filename="task-contract.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
    )


# delegation-matrix の "regions"/"examples"、task-contract の "gates"/"examples"、
# transition-screening の "types"/"examples" は axis ではなくルックアップ/データ group
# なので summarize から除外する。four-layer の "efficacy" は axis と並列の独立 group。
_NON_AXIS_GROUPS = {"regions", "examples", "gates", "types"}


def summarize_transition(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    # The 3 screening axes (technical_exposure / human_necessity /
    # demand_elasticity) score like matrix axes (absolute threshold over
    # question leaves); "types" and "examples" are lookup/data groups and
    # are excluded via _NON_AXIS_GROUPS.
    return _summarize(
        name="transition-screening",
        default_filename="transition-screening.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
    )


def _summarize(
    name: str,
    default_filename: str,
    overlay_paths: list[str | Path] | None,
    definition_path: str | Path | None,
    is_axes: bool,
) -> DefinitionSummary:
    overlay_paths = overlay_paths or []
    base_path = Path(definition_path) if definition_path else DEFAULT_DEFINITIONS_DIR / default_filename
    base = overlay_mod.load_yaml(base_path)

    if overlay_paths:
        result = overlay_mod.apply_overlays(base, overlay_paths)
        if not result.ok:
            from .check_readiness import OverlayError
            raise OverlayError(result.violations)
        merged = result.merged
        applied = [str(p) for p in overlay_paths]
    else:
        merged = base
        applied = []

    summary = DefinitionSummary(
        name=name,
        base_path=str(base_path),
        overlays_applied=applied,
    )

    base_groups = overlay_mod.group_items(base)
    merged_groups = overlay_mod.group_items(merged)
    threshold_keys = ("threshold",) if is_axes else ("pass", "revise")

    if is_axes:
        # delegation-matrix: regions/examples はデータ group なので axis から除外。
        for group_id, group in merged_groups.items():
            if group_id in _NON_AXIS_GROUPS:
                continue
            summary.axes.append(
                _summarize_group(group_id, group, base_groups.get(group_id), threshold_keys)
            )
    else:
        # four-layer: header の role でゲート層 (layers) と並列軸 (parallel_axes) に振り分ける。
        # efficacy / organization は並列軸として同じ枠で要約する(overlay で add/strengthen 可能)。
        from .check_readiness import axis_role, ROLE_PARALLEL

        for group_id, group in merged_groups.items():
            summary_item = _summarize_group(
                group_id, group, base_groups.get(group_id), threshold_keys
            )
            if axis_role(group_id, group["header"] or {}) == ROLE_PARALLEL:
                summary.parallel_axes.append(summary_item)
            else:
                summary.layers.append(summary_item)
    return summary


def _summarize_group(
    group_id: str, group: dict, base_group: dict | None, threshold_keys: tuple[str, ...]
) -> LayerSummary:
    header = group["header"] or {}
    base_header = (base_group or {}).get("header") or {}
    base_leaves = (base_group or {}).get("leaves") or []
    thresholds = {k: header[k] for k in threshold_keys if k in header}
    base_thresholds = {k: base_header[k] for k in threshold_keys if k in base_header}
    # Count only presence questions. Existing definitions have no ``kind`` on
    # their leaves, so they default to "question"; task-contract's ``kind: data``
    # leaves (scorer.type, scorer.iruler_double_eval) are not counted.
    question_leaves = [
        leaf for leaf in group["leaves"] if leaf.get("kind", "question") == "question"
    ]
    return LayerSummary(
        id=group_id,
        name=header.get("name_ja") or header.get("name") or group_id,
        question_count=len(question_leaves),
        thresholds=thresholds,
        added_question_ids=_added_ids(base_leaves, group["leaves"]),
        strengthened_thresholds=_strengthened_thresholds(base_thresholds, thresholds),
    )


def _added_ids(base_items: list[dict], merged_items: list[dict]) -> list[str]:
    base_ids = {item["id"] for item in base_items if isinstance(item, dict) and "id" in item}
    return [item["id"] for item in merged_items if isinstance(item, dict) and item.get("id") not in base_ids]


def _strengthened_thresholds(base: dict, merged: dict) -> dict:
    out = {}
    for k, v in merged.items():
        if base.get(k) != v:
            out[k] = {"from": base.get(k), "to": v}
    return out


def render_text(summary: DefinitionSummary) -> str:
    lines = [
        f"definition: {summary.name}",
        f"base:       {summary.base_path}",
    ]
    if summary.overlays_applied:
        lines.append("overlays:")
        for o in summary.overlays_applied:
            lines.append(f"  - {o}")
    else:
        lines.append("overlays:   (none)")
    if summary.layers:
        lines.append("")
        lines.append("layers:")
        for layer in summary.layers:
            lines.append(
                f"  {layer.id} {layer.name}: {layer.question_count} questions, "
                f"thresholds={layer.thresholds}"
            )
            if layer.added_question_ids:
                lines.append(f"    +added: {', '.join(layer.added_question_ids)}")
            if layer.strengthened_thresholds:
                lines.append(f"    !strengthened: {layer.strengthened_thresholds}")
    if summary.axes:
        lines.append("")
        lines.append("axes:")
        for a in summary.axes:
            lines.append(
                f"  {a.id} {a.name}: {a.question_count} questions, {a.thresholds}"
            )
            if a.added_question_ids:
                lines.append(f"    +added: {', '.join(a.added_question_ids)}")
            if a.strengthened_thresholds:
                lines.append(f"    !strengthened: {a.strengthened_thresholds}")
    if summary.parallel_axes:
        lines.append("")
        lines.append("parallel_axes:")
        for e in summary.parallel_axes:
            lines.append(
                f"  {e.id} {e.name}: {e.question_count} questions, thresholds={e.thresholds}"
            )
            if e.added_question_ids:
                lines.append(f"    +added: {', '.join(e.added_question_ids)}")
            if e.strengthened_thresholds:
                lines.append(f"    !strengthened: {e.strengthened_thresholds}")
    return "\n".join(lines)


def render_json(summary: DefinitionSummary) -> str:
    return json.dumps(
        {
            "name": summary.name,
            "base": summary.base_path,
            "overlays": summary.overlays_applied,
            "layers": [
                {
                    "id": layer.id,
                    "name": layer.name,
                    "question_count": layer.question_count,
                    "thresholds": layer.thresholds,
                    "added_question_ids": layer.added_question_ids,
                    "strengthened_thresholds": layer.strengthened_thresholds,
                }
                for layer in summary.layers
            ],
            "axes": [
                {
                    "id": a.id,
                    "name": a.name,
                    "question_count": a.question_count,
                    "thresholds": a.thresholds,
                    "added_question_ids": a.added_question_ids,
                    "strengthened_thresholds": a.strengthened_thresholds,
                }
                for a in summary.axes
            ],
            "parallel_axes": [
                {
                    "id": a.id,
                    "name": a.name,
                    "question_count": a.question_count,
                    "thresholds": a.thresholds,
                    "added_question_ids": a.added_question_ids,
                    "strengthened_thresholds": a.strengthened_thresholds,
                }
                for a in summary.parallel_axes
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
