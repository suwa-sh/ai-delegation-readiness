"""Score business judgments against the delegation matrix.

Input YAML structure::

    judgments:
      - id: receipt_check
        description: Receipt mandatory items check
        answers:
          verifiability.V1: yes
          verifiability.V2: yes
          verifiability.V3: yes
          answer_definability.A1: yes
          answer_definability.A2: yes
          answer_definability.A3: yes

The output lists each judgment with its (verifiability, answer_definability)
pair (high or low) and the region (green / yellow / red).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import overlay_scoring as overlay_mod
from .check_readiness import OverlayError, _normalize_yes

DEFINITION_NAME = "delegation-matrix"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "delegation-matrix.yaml"


@dataclass
class AxisScore:
    axis_id: str
    score: int
    threshold: int
    level: str  # high | low
    yes_ids: list[str] = field(default_factory=list)
    no_ids: list[str] = field(default_factory=list)


@dataclass
class JudgmentResult:
    id: str
    description: str
    axes: dict[str, AxisScore]
    region: str  # green | yellow | red
    rationale: str


@dataclass
class ScoreResult:
    judgments: list[JudgmentResult]

    @property
    def conclusion_exit_code(self) -> int:
        regions = {j.region for j in self.judgments}
        if "red" in regions:
            return 2
        if "yellow" in regions:
            return 1
        return 0


# axes / regions / examples 以外の追加 group が将来生えても axis として扱えるよう、
# 予約された非 axis group id はここに列挙する (regions は評価用ルックアップ、examples はデータ)。
_NON_AXIS_GROUPS = {"regions", "examples"}


def _score_axis(axis_id: str, questions: list[dict], header: dict, answers: dict[str, Any]) -> AxisScore:
    yes_ids: list[str] = []
    no_ids: list[str] = []
    for q in questions:
        qid = q["id"]
        ans = _normalize_yes(answers.get(qid))
        if ans is True:
            yes_ids.append(qid)
        elif ans is False:
            no_ids.append(qid)
    threshold = int(header.get("threshold", len(questions)))
    score = len(yes_ids)
    level = "high" if score >= threshold else "low"
    return AxisScore(
        axis_id=axis_id,
        score=score,
        threshold=threshold,
        level=level,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )


def _resolve_region(region_leaves: list[dict], axis_levels: dict[str, str], sep: str) -> dict:
    """Find the region whose ``when`` clause matches the axis level pair.

    Region leaves keep their source order (green/yellow/red), evaluated in
    that order. The returned ``id`` is the local slug (e.g. ``green``), not
    the full item id (``regions.green``).
    """
    for leaf in region_leaves:
        when_clauses = leaf["when"]
        if isinstance(when_clauses, dict):
            when_clauses = [when_clauses]
        for clause in when_clauses:
            if all(axis_levels.get(k) == v for k, v in clause.items()):
                return {**leaf, "id": leaf["id"].split(sep, 1)[1]}
    raise ValueError(f"no region matches axis levels: {axis_levels}")


def score(
    judgments_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> ScoreResult:
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
    region_leaves = groups["regions"]["leaves"]

    input_data = overlay_mod.load_yaml(judgments_path)
    judgments_in = input_data.get("judgments", []) or []

    results: list[JudgmentResult] = []
    for j in judgments_in:
        jid = j.get("id") or j.get("description", "<unnamed>")
        desc = j.get("description") or jid
        answers = j.get("answers", {}) or {}
        axis_scores = {
            aid: _score_axis(aid, group["leaves"], group["header"], answers)
            for aid, group in axis_groups.items()
        }
        axis_levels = {aid: s.level for aid, s in axis_scores.items()}
        region = _resolve_region(region_leaves, axis_levels, sep)
        results.append(
            JudgmentResult(
                id=jid,
                description=desc,
                axes=axis_scores,
                region=region["id"],
                rationale=region.get("action", "").strip(),
            )
        )
    return ScoreResult(judgments=results)


def render_text(result: ScoreResult) -> str:
    if not result.judgments:
        return "No judgments scored."
    lines = []
    for j in result.judgments:
        marker = _region_marker(j.region)
        axis_summary = ", ".join(
            f"{aid}={s.level}({s.score}/{len(s.yes_ids) + len(s.no_ids) or s.threshold})"
            for aid, s in j.axes.items()
        )
        lines.append(f"{marker} {j.id}: {j.region.upper()}  ({axis_summary})")
        lines.append(f"    {j.description}")
        lines.append(f"    action: {j.rationale}")
    return "\n".join(lines)


def render_json(result: ScoreResult) -> str:
    payload = {
        "judgments": [
            {
                "id": j.id,
                "description": j.description,
                "region": j.region,
                "axes": {
                    aid: {
                        "score": s.score,
                        "threshold": s.threshold,
                        "level": s.level,
                        "yes": s.yes_ids,
                        "no": s.no_ids,
                    }
                    for aid, s in j.axes.items()
                },
                "action": j.rationale,
            }
            for j in result.judgments
        ],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _region_marker(region: str) -> str:
    return {"green": "[GREEN ]", "yellow": "[YELLOW]", "red": "[RED   ]"}.get(region, "[?     ]")
