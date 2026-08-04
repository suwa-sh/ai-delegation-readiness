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
    # Lookup-only groups (patch-decision の discard_reason / bands) は question を
    # 持たない。件数を "0 questions" と出すと追加済みの leaf と矛盾して読めるため、
    # leaf 総数を保持して表示語を切り替える。
    leaf_count: int = 0
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
# patch-decision の "decision"/"reading" は overlay 不可の規範 group なので同様に除外し、
# 拡張できる discard_reason / bands だけを表示する。
_NON_AXIS_GROUPS = {"regions", "examples", "gates", "types", "decision", "reading"}


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


def summarize_risk_architecture(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    # profile / scenario_* / owners are all question groups scored by the
    # assess module's own monotone-pair logic; there is no lookup group.
    # Contract validation (exactly-two questions per capability etc.) is
    # enforced here too, so a broken overlay cannot slip through the listing.
    from .assess_risk_architecture import validate_overlay_files

    validate_overlay_files(overlay_paths or [])
    summary = _summarize(
        name="risk-architecture",
        default_filename="risk-architecture.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
        risk_contract=True,
    )
    return summary


def summarize_patch_ownership(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    return _summarize(
        name="patch-ownership",
        default_filename="patch-ownership.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
        patch_contract=True,
    )


def summarize_patch_decision(
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> DefinitionSummary:
    return _summarize(
        name="patch-decision",
        default_filename="patch-decision.yaml",
        overlay_paths=overlay_paths,
        definition_path=definition_path,
        is_axes=True,
        decision_contract=True,
    )


def _summarize(
    name: str,
    default_filename: str,
    overlay_paths: list[str | Path] | None,
    definition_path: str | Path | None,
    is_axes: bool,
    patch_contract: bool = False,
    decision_contract: bool = False,
    risk_contract: bool = False,
) -> DefinitionSummary:
    overlay_paths = overlay_paths or []
    base_path = Path(definition_path) if definition_path else DEFAULT_DEFINITIONS_DIR / default_filename
    base = overlay_mod.load_yaml(base_path)
    if patch_contract:
        from .check_patch_ownership import merge_definition

        merged = merge_definition(base, overlay_paths)
    elif decision_contract:
        from .summarize_patch_decisions import _resolve_definition, load_bands

        merged = _resolve_definition(overlay_paths) if overlay_paths else base
        # 不正な band を一覧表示で素通りさせない(summarize と同じ契約)
        load_bands(merged)
    else:
        merged = _merge_overlays(base, overlay_paths)
    if risk_contract:
        # 形状の崩れた定義を一覧表示で素通りさせない(assess と同じ契約)
        from .assess_risk_architecture import InputError, validate_contract

        problems = validate_contract(merged)
        if problems:
            raise InputError(
                "definition violates the risk-architecture contract: " + "; ".join(problems)
            )

    summary = DefinitionSummary(
        name=name,
        base_path=str(base_path),
        overlays_applied=[str(p) for p in overlay_paths],
    )

    base_groups = overlay_mod.group_items(base)
    merged_groups = overlay_mod.group_items(merged)
    if risk_contract:
        # risk-architecture groups carry band thresholds instead of a single
        # per-axis threshold (profile: hybrid_min/ai_native_min, scenarios:
        # medium_min/high_min); show whichever the header defines.
        threshold_keys = ("medium_min", "high_min", "hybrid_min", "ai_native_min")
    else:
        threshold_keys = ("threshold",) if is_axes else ("pass", "revise")

    if is_axes:
        _fill_axes(summary, merged_groups, base_groups, threshold_keys)
    else:
        _fill_layers(summary, merged_groups, base_groups, threshold_keys)
    return summary


def _merge_overlays(base: dict, overlay_paths: list[str | Path]) -> dict:
    if not overlay_paths:
        return base
    result = overlay_mod.apply_overlays(base, overlay_paths)
    if not result.ok:
        from .check_readiness import OverlayError
        raise OverlayError(result.violations)
    return result.merged


def _fill_axes(
    summary: DefinitionSummary,
    merged_groups: dict,
    base_groups: dict,
    threshold_keys: tuple[str, ...],
) -> None:
    """delegation-matrix: regions/examples はデータ group なので axis から除外。"""
    for group_id, group in merged_groups.items():
        if group_id in _NON_AXIS_GROUPS:
            continue
        summary.axes.append(
            _summarize_group(group_id, group, base_groups.get(group_id), threshold_keys)
        )


def _fill_layers(
    summary: DefinitionSummary,
    merged_groups: dict,
    base_groups: dict,
    threshold_keys: tuple[str, ...],
) -> None:
    """four-layer: header の role でゲート層と並列軸に振り分ける。

    efficacy / organization は並列軸として同じ枠で要約する(overlay で
    add/strengthen 可能)。
    """
    from .check_readiness import axis_role, ROLE_PARALLEL

    for group_id, group in merged_groups.items():
        summary_item = _summarize_group(
            group_id, group, base_groups.get(group_id), threshold_keys
        )
        if axis_role(group_id, group["header"] or {}) == ROLE_PARALLEL:
            summary.parallel_axes.append(summary_item)
        else:
            summary.layers.append(summary_item)


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
        leaf_count=len(group["leaves"]),
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


def _render_section(
    title: str, items: list[LayerSummary], *, label_thresholds: bool
) -> list[str]:
    """Render one summary section, or nothing when the section is empty.

    ``label_thresholds`` keeps the historical difference in the axes section,
    which prints the thresholds bare while layers/parallel_axes prefix them.
    """
    if not items:
        return []
    lines = ["", f"{title}:"]
    for item in items:
        thresholds = f"thresholds={item.thresholds}" if label_thresholds else f"{item.thresholds}"
        # question を持たない lookup group は entries で数える
        if item.question_count == 0 and item.leaf_count > 0:
            count = f"{item.leaf_count} entries"
        else:
            count = f"{item.question_count} questions"
        lines.append(f"  {item.id} {item.name}: {count}, {thresholds}")
        if item.added_question_ids:
            lines.append(f"    +added: {', '.join(item.added_question_ids)}")
        if item.strengthened_thresholds:
            lines.append(f"    !strengthened: {item.strengthened_thresholds}")
    return lines


def render_text(summary: DefinitionSummary) -> str:
    lines = [
        f"definition: {summary.name}",
        f"base:       {summary.base_path}",
    ]
    if summary.overlays_applied:
        lines.append("overlays:")
        lines.extend(f"  - {o}" for o in summary.overlays_applied)
    else:
        lines.append("overlays:   (none)")
    lines.extend(_render_section("layers", summary.layers, label_thresholds=True))
    lines.extend(_render_section("axes", summary.axes, label_thresholds=False))
    lines.extend(
        _render_section("parallel_axes", summary.parallel_axes, label_thresholds=True)
    )
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
