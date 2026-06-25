"""Score business judgments against the delegation matrix.

Input YAML structure::

    judgments:
      - id: receipt_check
        description: Receipt mandatory items check
        answers:
          V1: yes
          V2: yes
          V3: yes
          A1: yes
          A2: yes
          A3: yes

The output lists each judgment with its (verifiability, answer_definability)
pair (high or low) and the region (green / yellow / red).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import overlay as overlay_mod
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


def _score_axis(axis: dict, answers: dict[str, Any]) -> AxisScore:
    yes_ids: list[str] = []
    no_ids: list[str] = []
    for q in axis["questions"]:
        qid = q["id"]
        ans = _normalize_yes(answers.get(qid))
        if ans is True:
            yes_ids.append(qid)
        elif ans is False:
            no_ids.append(qid)
    threshold = int(axis.get("threshold", len(axis["questions"])))
    score = len(yes_ids)
    level = "high" if score >= threshold else "low"
    return AxisScore(
        axis_id=axis["id"],
        score=score,
        threshold=threshold,
        level=level,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )


def _resolve_region(regions: list[dict], axis_levels: dict[str, str]) -> dict:
    """Find the region whose ``when`` clause matches the axis level pair."""
    for region in regions:
        when_clauses = region["when"]
        if isinstance(when_clauses, dict):
            when_clauses = [when_clauses]
        for clause in when_clauses:
            if all(axis_levels.get(k) == v for k, v in clause.items()):
                return region
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

    input_data = overlay_mod.load_yaml(judgments_path)
    judgments_in = input_data.get("judgments", []) or []

    results: list[JudgmentResult] = []
    for j in judgments_in:
        jid = j.get("id") or j.get("description", "<unnamed>")
        desc = j.get("description") or jid
        answers = j.get("answers", {}) or {}
        axis_scores = {axis["id"]: _score_axis(axis, answers) for axis in defn["axes"]}
        axis_levels = {aid: s.level for aid, s in axis_scores.items()}
        region = _resolve_region(defn["regions"], axis_levels)
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
