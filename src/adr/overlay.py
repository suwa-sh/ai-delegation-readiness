"""Overlay loading and merge logic.

Merge rules (enforced):
- ``add``        : append items to a list. Existing items must not be touched.
- ``strengthen`` : update a numeric threshold to a stricter (higher) value.

Any other change (delete, replace, weaken) is a rule violation and rejected.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class MergeViolation:
    """A single rule-violation detected while applying an overlay."""

    path: str
    kind: str
    message: str


@dataclass
class MergeResult:
    """Outcome of applying overlays to a base definition."""

    merged: dict
    applied: list[str] = field(default_factory=list)
    violations: list[MergeViolation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def load_yaml(path: str | Path) -> dict:
    """Load a YAML file into a dict. Raises on syntax errors."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _index_by_id(items: list[dict]) -> dict[str, dict]:
    return {item["id"]: item for item in items if isinstance(item, dict) and "id" in item}


def _apply_layer_overlay(
    base_layers: list[dict],
    overlay_layers: list[dict],
    violations: list[MergeViolation],
) -> list[dict]:
    """Merge ``overlay.layers[]`` into ``base.layers[]``.

    Each overlay layer must reference a base layer by ``id`` and may carry
    ``add_questions`` and/or ``strengthen_thresholds``. Anything else is a
    violation.
    """
    merged_layers = [deepcopy(layer) for layer in base_layers]
    layer_index = _index_by_id(merged_layers)

    for overlay_layer in overlay_layers:
        if not isinstance(overlay_layer, dict) or "id" not in overlay_layer:
            violations.append(
                MergeViolation(
                    path="layers[]",
                    kind="invalid_overlay",
                    message="each overlay layer entry needs an 'id' field",
                )
            )
            continue
        layer_id = overlay_layer["id"]
        if layer_id not in layer_index:
            violations.append(
                MergeViolation(
                    path=f"layers[{layer_id}]",
                    kind="unknown_id",
                    message=f"layer id '{layer_id}' is not in the base definition",
                )
            )
            continue

        base_layer = layer_index[layer_id]
        for key, value in overlay_layer.items():
            if key == "id":
                continue
            if key == "add_questions":
                _apply_add(
                    base_layer,
                    "questions",
                    value,
                    path=f"layers[{layer_id}].questions",
                    violations=violations,
                )
            elif key == "strengthen_thresholds":
                _apply_strengthen(
                    base_layer,
                    "verdict_thresholds",
                    value,
                    path=f"layers[{layer_id}].verdict_thresholds",
                    violations=violations,
                )
            else:
                violations.append(
                    MergeViolation(
                        path=f"layers[{layer_id}].{key}",
                        kind="unsupported_op",
                        message=(
                            f"overlay key '{key}' is not supported; only "
                            "add_questions and strengthen_thresholds are allowed"
                        ),
                    )
                )
    return merged_layers


def _apply_add(
    target: dict,
    list_key: str,
    new_items: list[dict],
    *,
    path: str,
    violations: list[MergeViolation],
) -> None:
    """Append new items to ``target[list_key]``, refusing id collisions."""
    if not isinstance(new_items, list):
        violations.append(
            MergeViolation(
                path=path,
                kind="invalid_overlay",
                message=f"add value at {path} must be a list",
            )
        )
        return

    existing = target.setdefault(list_key, [])
    existing_ids = {item.get("id") for item in existing if isinstance(item, dict)}
    for item in new_items:
        if not isinstance(item, dict) or "id" not in item:
            violations.append(
                MergeViolation(
                    path=path,
                    kind="invalid_overlay",
                    message=f"each added item at {path} needs an 'id'",
                )
            )
            continue
        if item["id"] in existing_ids:
            violations.append(
                MergeViolation(
                    path=path,
                    kind="id_collision",
                    message=(
                        f"added id '{item['id']}' at {path} collides with an existing item; "
                        "use a unique id (overwrite is not allowed)"
                    ),
                )
            )
            continue
        existing.append(deepcopy(item))
        existing_ids.add(item["id"])  # 同一 overlay 内の重複検出のため追跡を続ける


def _apply_strengthen(
    target: dict,
    key: str,
    new_thresholds: dict,
    *,
    path: str,
    violations: list[MergeViolation],
) -> None:
    """Update ``target[key]`` thresholds to stricter values only.

    For verdict thresholds, "stricter" means a higher numeric value (a
    higher fraction of questions must answer yes).
    """
    if not isinstance(new_thresholds, dict):
        violations.append(
            MergeViolation(
                path=path,
                kind="invalid_overlay",
                message=f"strengthen value at {path} must be a mapping",
            )
        )
        return

    existing = target.setdefault(key, {})
    for k, v in new_thresholds.items():
        if k not in existing:
            existing[k] = v
            continue
        old = existing[k]
        try:
            if float(v) < float(old):
                violations.append(
                    MergeViolation(
                        path=f"{path}.{k}",
                        kind="weakening_rejected",
                        message=(
                            f"strengthen at {path}.{k} would weaken the threshold "
                            f"from {old} to {v}; only stricter (>=) values are accepted"
                        ),
                    )
                )
                continue
        except (TypeError, ValueError):
            violations.append(
                MergeViolation(
                    path=f"{path}.{k}",
                    kind="invalid_overlay",
                    message=f"strengthen value at {path}.{k} must be numeric",
                )
            )
            continue
        existing[k] = v


def _apply_axes_overlay(
    base_axes: list[dict],
    overlay_axes: list[dict],
    violations: list[MergeViolation],
) -> list[dict]:
    """Merge overlay axes (delegation-matrix specific)."""
    merged = [deepcopy(axis) for axis in base_axes]
    axis_index = _index_by_id(merged)
    for overlay_axis in overlay_axes:
        if not isinstance(overlay_axis, dict) or "id" not in overlay_axis:
            violations.append(
                MergeViolation(
                    path="axes[]",
                    kind="invalid_overlay",
                    message="each overlay axis entry needs an 'id'",
                )
            )
            continue
        axis_id = overlay_axis["id"]
        if axis_id not in axis_index:
            violations.append(
                MergeViolation(
                    path=f"axes[{axis_id}]",
                    kind="unknown_id",
                    message=f"axis id '{axis_id}' is not in the base definition",
                )
            )
            continue
        base_axis = axis_index[axis_id]
        for key, value in overlay_axis.items():
            if key == "id":
                continue
            if key == "add_questions":
                _apply_add(
                    base_axis,
                    "questions",
                    value,
                    path=f"axes[{axis_id}].questions",
                    violations=violations,
                )
            elif key == "strengthen_threshold":
                old = base_axis.get("threshold")
                try:
                    if old is not None and float(value) < float(old):
                        violations.append(
                            MergeViolation(
                                path=f"axes[{axis_id}].threshold",
                                kind="weakening_rejected",
                                message=(
                                    f"threshold for axis {axis_id} cannot be weakened "
                                    f"from {old} to {value}"
                                ),
                            )
                        )
                        continue
                except (TypeError, ValueError):
                    violations.append(
                        MergeViolation(
                            path=f"axes[{axis_id}].threshold",
                            kind="invalid_overlay",
                            message=f"strengthen_threshold must be numeric",
                        )
                    )
                    continue
                base_axis["threshold"] = value
            else:
                violations.append(
                    MergeViolation(
                        path=f"axes[{axis_id}].{key}",
                        kind="unsupported_op",
                        message=(
                            f"overlay key '{key}' is not supported on axes; only "
                            "add_questions and strengthen_threshold are allowed"
                        ),
                    )
                )
    return merged


def apply_overlay(base: dict, overlay: dict) -> MergeResult:
    """Apply a single overlay onto ``base`` and return the merged definition.

    The base definition must declare ``extension_points`` and have a
    ``name`` that matches the overlay's ``extends`` field.
    """
    violations: list[MergeViolation] = []

    if overlay.get("extends") != base.get("name"):
        violations.append(
            MergeViolation(
                path="extends",
                kind="extends_mismatch",
                message=(
                    f"overlay extends '{overlay.get('extends')}' does not match "
                    f"base name '{base.get('name')}'"
                ),
            )
        )
        return MergeResult(merged=deepcopy(base), violations=violations)

    merged = deepcopy(base)

    if "layers" in overlay:
        if "layers" not in base:
            violations.append(
                MergeViolation(
                    path="layers",
                    kind="unsupported_op",
                    message="base definition does not have layers",
                )
            )
        else:
            merged["layers"] = _apply_layer_overlay(
                base["layers"], overlay["layers"], violations
            )

    if "axes" in overlay:
        if "axes" not in base:
            violations.append(
                MergeViolation(
                    path="axes",
                    kind="unsupported_op",
                    message="base definition does not have axes",
                )
            )
        else:
            merged["axes"] = _apply_axes_overlay(
                base["axes"], overlay["axes"], violations
            )

    if "add_examples" in overlay:
        _apply_add(
            merged,
            "examples",
            overlay["add_examples"],
            path="examples",
            violations=violations,
        )

    if "efficacy_axis" in overlay:
        if "efficacy_axis" not in base:
            violations.append(
                MergeViolation(
                    path="efficacy_axis",
                    kind="unsupported_op",
                    message="base definition does not have efficacy_axis",
                )
            )
        else:
            ov = overlay["efficacy_axis"]
            if not isinstance(ov, dict):
                violations.append(
                    MergeViolation(
                        path="efficacy_axis",
                        kind="invalid_overlay",
                        message="efficacy_axis overlay must be a mapping",
                    )
                )
            else:
                for key, value in ov.items():
                    if key == "add_questions":
                        _apply_add(
                            merged["efficacy_axis"],
                            "questions",
                            value,
                            path="efficacy_axis.questions",
                            violations=violations,
                        )
                    elif key == "strengthen_thresholds":
                        _apply_strengthen(
                            merged["efficacy_axis"],
                            "verdict_thresholds",
                            value,
                            path="efficacy_axis.verdict_thresholds",
                            violations=violations,
                        )
                    else:
                        violations.append(
                            MergeViolation(
                                path=f"efficacy_axis.{key}",
                                kind="unsupported_op",
                                message=(
                                    f"efficacy_axis overlay key '{key}' is not supported; "
                                    "only add_questions and strengthen_thresholds are allowed"
                                ),
                            )
                        )

    for key in overlay:
        if key in {"version", "extends", "layers", "axes", "add_examples", "efficacy_axis"}:
            continue
        violations.append(
            MergeViolation(
                path=key,
                kind="unsupported_op",
                message=f"overlay top-level key '{key}' is not supported",
            )
        )

    return MergeResult(merged=merged, violations=violations)


def apply_overlays(base: dict, overlay_paths: list[str | Path]) -> MergeResult:
    """Apply multiple overlays in order, accumulating violations."""
    current = deepcopy(base)
    applied: list[str] = []
    all_violations: list[MergeViolation] = []
    for path in overlay_paths:
        overlay = load_yaml(path)
        result = apply_overlay(current, overlay)
        all_violations.extend(result.violations)
        if result.violations:
            return MergeResult(merged=result.merged, applied=applied, violations=all_violations)
        current = result.merged
        applied.append(str(path))
    return MergeResult(merged=current, applied=applied, violations=all_violations)
