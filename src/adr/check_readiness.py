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
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

import overlay_scoring as overlay_mod

DEFINITION_NAME = "four-layer-delegation-readiness"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "four-layer.yaml"


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
    efficacy: AxisResult
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
        if normalized in {"yes", "y", "true", "1"}:
            return True
        if normalized in {"no", "n", "false", "0"}:
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

    target = overlay_mod.load_yaml(target_path)
    answers = target.get("answers", {}) or {}

    # 層(L1..L4)は efficacy と並列の独立 group。source order を保つ
    # group_items() のキー順で、efficacy 以外を層として扱う。
    groups = overlay_mod.group_items(defn)
    layer_results = [
        _score_axis(
            axis_id=group_id,
            axis_name=group["header"].get("name_ja") or group["header"].get("name"),
            questions=group["leaves"],
            header=group["header"],
            answers=answers,
        )
        for group_id, group in groups.items()
        if group_id != "efficacy"
    ]

    blocked_from: str | None = None
    for layer in layer_results:
        if blocked_from is None and layer.verdict != "pass":
            blocked_from = layer.id

    efficacy_group = groups["efficacy"]
    efficacy_header = efficacy_group["header"]
    efficacy_result = _score_axis(
        axis_id="efficacy",
        axis_name=efficacy_header.get("name_ja") or efficacy_header.get("name"),
        questions=efficacy_group["leaves"],
        header=efficacy_header,
        answers=answers,
    )

    overall_axes = layer_results + [efficacy_result]
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
        efficacy=efficacy_result,
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
            lines.append(f"    -> upper layers are gated by this verdict")
    bar = _verdict_marker(result.efficacy.verdict)
    lines.append(
        f"{bar} efficacy {result.efficacy.name}: {result.efficacy.verdict.upper()} "
        f"({int(result.efficacy.score * 100)}%)"
    )
    if result.efficacy.no_ids:
        lines.append(f"    no: {', '.join(result.efficacy.no_ids)}")
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
        "layers": [_axis_to_dict(l) for l in result.layers],
        "efficacy": _axis_to_dict(result.efficacy),
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


def exit_code_for(result: CheckResult) -> int:
    return {"PASS": 0, "REVISE": 1, "BLOCK": 2}[result.conclusion]
