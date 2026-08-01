"""Gate an AI-generated patch by ownership cost and acceptance evidence."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import overlay_scoring as overlay_mod

from .check_readiness import OverlayError, _normalize_yes

DEFINITION_NAME = "patch-ownership"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "patch-ownership.yaml"
SCHEMA_VERSION = "1"
_OTHERWISE = "otherwise"
_TEST_STATUS_ID = "evidence.test_status"
_TEST_REF_ID = "evidence.test_ref"
_TEST_NA_REF_ID = "evidence.test_na_ref"
_OWNER_REF_ID = "ownership.owner_ref"
_REVIEW_ROUTE_REF_ID = "ownership.review_route_ref"
_PLACEHOLDERS = {"x", "yes", "no", "n/a", "na", "none", "todo", "tbd"}
_REF_PATTERNS = (
    re.compile(r"git:[0-9a-f]{40}"),
    re.compile(r"file:[^#\s]+#sha256=[0-9a-f]{64}"),
    re.compile(r"https://\S+#sha256=[0-9a-f]{64}"),
    re.compile(r"ci:[A-Za-z0-9_.-]+:[A-Za-z0-9_.:/-]+#sha256=[0-9a-f]{64}"),
)
_OWNER_PATTERN = re.compile(r"(user|team|codeowners):(\S+)")


class InputError(Exception):
    """Patch input or the definition's gate policy is malformed."""


@dataclass
class GroupScore:
    id: str
    name: str
    score: int
    threshold: int
    level: str
    yes_ids: list[str] = field(default_factory=list)
    no_ids: list[str] = field(default_factory=list)


@dataclass
class PatchResult:
    patch: str
    groups: list[GroupScore]
    risk_ids: list[str]
    missing_controls: list[str]
    evidence_refs: dict[str, str]
    region: str
    region_name: str
    rationale: str
    exit_code: int
    active_conditions: list[str]


def _parse_answer_strict(value: Any) -> bool | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if value not in (0, 1):
            return None
    return _normalize_yes(value)


def _question_leaves(group: dict) -> list[dict]:
    return [leaf for leaf in group["leaves"] if leaf.get("kind", "question") == "question"]


def _parse_all_questions(groups: dict, answers: dict[str, Any]) -> dict[str, bool]:
    parsed: dict[str, bool] = {}
    missing: list[str] = []
    invalid: list[str] = []
    for gid in ("probe", "ownership", "hollow_green", "never_cheap"):
        if gid not in groups:
            raise InputError(f"definition is missing the '{gid}' group")
        for leaf in _question_leaves(groups[gid]):
            qid = leaf["id"]
            if qid not in answers:
                missing.append(qid)
                continue
            value = _parse_answer_strict(answers[qid])
            if value is None:
                invalid.append(f"{qid} (got: {answers[qid]!r})")
            else:
                parsed[qid] = value
    if missing:
        raise InputError(f"missing required yes/no answer(s): {', '.join(sorted(missing))}")
    if invalid:
        raise InputError(f"invalid yes/no answer(s): {', '.join(sorted(invalid))}")
    return parsed


def _score_required_group(
    group_id: str,
    group: dict,
    parsed: dict[str, bool],
    required_ids: set[str],
) -> GroupScore:
    header = group["header"] or {}
    questions = [q for q in _question_leaves(group) if q["id"] in required_ids]
    yes_ids = [q["id"] for q in questions if parsed[q["id"]]]
    no_ids = [q["id"] for q in questions if not parsed[q["id"]]]
    threshold = len(questions)
    score = len(yes_ids)
    if score >= threshold:
        level = "present"
    else:
        level = "partial" if score else "absent"
    return GroupScore(
        id=group_id,
        name=header.get("name_ja") or header.get("name") or group_id,
        score=score,
        threshold=threshold,
        level=level,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )


def _score_hollow_group(group: dict, parsed: dict[str, bool]) -> GroupScore:
    header = group["header"] or {}
    questions = _question_leaves(group)
    yes_ids = [q["id"] for q in questions if parsed[q["id"]]]
    no_ids = [q["id"] for q in questions if not parsed[q["id"]]]
    anchor = any(
        parsed[q["id"]] for q in questions if q.get("gate_role") == "anchor"
    )
    alternative = any(
        parsed[q["id"]] for q in questions if q.get("gate_role") == "alternative"
    )
    score = int(anchor) + int(alternative)
    if score == 2:
        level = "present"
    else:
        level = "partial" if score else "absent"
    return GroupScore(
        id="hollow_green",
        name=header.get("name_ja") or header.get("name") or "hollow_green",
        score=score,
        threshold=2,
        level=level,
        yes_ids=yes_ids,
        no_ids=no_ids,
    )


def _base_and_added_question_ids(base: dict, merged: dict, group_id: str) -> tuple[set[str], set[str]]:
    base_group = overlay_mod.group_items(base).get(group_id, {"leaves": []})
    merged_group = overlay_mod.group_items(merged).get(group_id, {"leaves": []})
    base_ids = {leaf["id"] for leaf in _question_leaves(base_group)}
    merged_ids = {leaf["id"] for leaf in _question_leaves(merged_group)}
    return base_ids, merged_ids - base_ids


def validate_overlay_contract(base: dict, merged: dict) -> list[str]:
    """Validate patch-ownership semantics that the generic engine cannot infer."""
    errors: list[str] = []
    base_groups = overlay_mod.group_items(base)
    merged_groups = overlay_mod.group_items(merged)
    for gid in ("probe", "ownership", "never_cheap"):
        base_ids = {leaf["id"] for leaf in base_groups[gid]["leaves"]}
        for leaf in merged_groups[gid]["leaves"]:
            if leaf["id"] in base_ids:
                continue
            if leaf.get("kind", "question") != "question":
                errors.append(f"{leaf['id']}: added {gid} leaf must be kind: question")
    if merged_groups.get("hollow_green") != base_groups.get("hollow_green"):
        errors.append("hollow_green: overlay extension is not supported")
    errors.extend(_threshold_contract_errors(merged_groups))
    return errors


def _threshold_contract_errors(groups: dict) -> list[str]:
    errors: list[str] = []
    for gid in ("probe", "ownership"):
        questions = _question_leaves(groups[gid])
        raw = (groups[gid]["header"] or {}).get("threshold", len(questions))
        if isinstance(raw, bool) or not isinstance(raw, int):
            errors.append(
                f"{gid}.threshold must be an integer (got {raw!r})"
            )
            continue
        threshold = raw
        if threshold < 1 or threshold > len(questions):
            errors.append(
                f"{gid}.threshold must be between 1 and {len(questions)} (got {threshold})"
            )
    return errors


def _validate_owner_ref(raw: Any) -> str:
    value = str(raw or "").strip()
    match = _OWNER_PATTERN.fullmatch(value)
    payload = match.group(2) if match else ""
    invalid_payload = (
        not payload
        or payload.lower() in _PLACEHOLDERS
        or "<" in payload
        or ">" in payload
    )
    if match is None or invalid_payload:
        raise InputError(
            f"'{_OWNER_REF_ID}' must be user:<id>, team:<id>, or codeowners:<path>"
        )
    if match.group(1) == "codeowners":
        owner_path = Path(payload)
        if owner_path.is_absolute() or ".." in owner_path.parts:
            raise InputError(
                f"'{_OWNER_REF_ID}' codeowners path must be relative without '..'"
            )
    return value


def _validate_evidence_ref(qid: str, raw: Any) -> str:
    value = str(raw or "").strip()
    if not value or value.lower() in _PLACEHOLDERS or "<" in value or ">" in value:
        raise InputError(f"'{qid}' must be a content-addressed evidence reference")
    if not any(pattern.fullmatch(value) for pattern in _REF_PATTERNS):
        raise InputError(
            f"'{qid}' must use git:<full-sha>, file:<path>#sha256=<64hex>, "
            "https://...#sha256=<64hex>, or ci:<provider>:<run-id>#sha256=<64hex>"
        )
    if value.startswith("file:"):
        relative_path = Path(value.removeprefix("file:").split("#", 1)[0])
        if relative_path.is_absolute() or ".." in relative_path.parts:
            raise InputError(f"'{qid}' file reference must use a relative path without '..'")
    return value


def _read_evidence(answers: dict[str, Any], high_risk: bool) -> tuple[dict[str, str], str]:
    owner = _validate_owner_ref(answers.get(_OWNER_REF_ID))
    refs = {"ownership.owner_ref": owner}
    for qid in ("evidence.patch_ref", "evidence.risk_manifest_ref"):
        refs[qid] = _validate_evidence_ref(qid, answers.get(qid))

    raw_status = answers.get(_TEST_STATUS_ID)
    if raw_status is None:
        raise InputError(f"'{_TEST_STATUS_ID}' is required")
    status = str(raw_status).strip().lower()
    if status not in {"present", "absent", "not_applicable"}:
        raise InputError(
            f"'{_TEST_STATUS_ID}' must be present, absent, or not_applicable"
        )
    refs[_TEST_STATUS_ID] = status
    if status == "present":
        refs[_TEST_REF_ID] = _validate_evidence_ref(
            _TEST_REF_ID, answers.get(_TEST_REF_ID)
        )
    elif status == "not_applicable":
        refs[_TEST_NA_REF_ID] = _validate_evidence_ref(
            _TEST_NA_REF_ID, answers.get(_TEST_NA_REF_ID)
        )
    if high_risk:
        raw_review_ref = str(answers.get(_REVIEW_ROUTE_REF_ID) or "").strip()
        if raw_review_ref:
            refs[_REVIEW_ROUTE_REF_ID] = _validate_evidence_ref(
                _REVIEW_ROUTE_REF_ID, raw_review_ref
            )
    return refs, status


def _required_ids(base: dict, merged: dict, metadata_key: str) -> set[str]:
    groups = overlay_mod.group_items(base)
    required = {
        leaf["id"]
        for group in groups.values()
        for leaf in _question_leaves(group)
        if leaf.get(metadata_key) is True
    }
    _, probe_added = _base_and_added_question_ids(base, merged, "probe")
    _, ownership_added = _base_and_added_question_ids(base, merged, "ownership")
    if metadata_key == "required_for_green":
        required |= probe_added | ownership_added
    if metadata_key == "required_when_high_risk":
        required |= ownership_added
    return required


def _hollow_green_holds(groups: dict, parsed: dict[str, bool]) -> bool:
    leaves = _question_leaves(groups["hollow_green"])
    anchors = [leaf["id"] for leaf in leaves if leaf.get("gate_role") == "anchor"]
    alternatives = [leaf["id"] for leaf in leaves if leaf.get("gate_role") == "alternative"]
    if not anchors or not alternatives:
        raise InputError("hollow_green must define anchor and alternative gate roles")
    return all(parsed[qid] for qid in anchors) and any(parsed[qid] for qid in alternatives)


def _cond_test_evidence_absent(ctx: dict) -> bool:
    return ctx["test_status"] == "absent"


def _cond_hollow_green_failed(ctx: dict) -> bool:
    return not ctx["hollow_green_holds"]


def _cond_high_risk_controls_missing(ctx: dict) -> bool:
    return bool(ctx["risk_ids"] and ctx["missing_high_risk_controls"])


def _cond_any_high_risk(ctx: dict) -> bool:
    return bool(ctx["risk_ids"])


def _cond_any_green_requirement_failed(ctx: dict) -> bool:
    return bool(ctx["missing_green_requirements"])


CONDITION_EVALUATORS: dict[str, Callable[[dict], bool]] = {
    "test_evidence_absent": _cond_test_evidence_absent,
    "hollow_green_failed": _cond_hollow_green_failed,
    "high_risk_controls_missing": _cond_high_risk_controls_missing,
    "any_high_risk": _cond_any_high_risk,
    "any_green_requirement_failed": _cond_any_green_requirement_failed,
}


def _resolve_region(gate_leaves: list[dict], ctx: dict, sep: str) -> dict:
    for leaf in gate_leaves:
        tokens = leaf.get("when", [])
        if isinstance(tokens, str):
            tokens = [tokens]
        for token in tokens:
            if token == _OTHERWISE:
                return {**leaf, "id": leaf["id"].split(sep, 1)[1]}
            evaluator = CONDITION_EVALUATORS.get(token)
            if evaluator is None:
                raise InputError(
                    f"gate leaf '{leaf['id']}' references unknown condition '{token}'"
                )
            if evaluator(ctx):
                return {**leaf, "id": leaf["id"].split(sep, 1)[1]}
    raise InputError("no gate region matched (gates require an otherwise fallback)")


def merge_definition(base: dict, overlay_paths: list[str | Path]) -> dict:
    if not overlay_paths:
        return base
    from . import io_input

    # The merge engine uses SafeLoader but accepts duplicate keys. Validate
    # user-controlled patch overlays first so last-key-wins cannot alter policy.
    for overlay_path in overlay_paths:
        overlay_data = io_input.load_yaml_unique(overlay_path)
        io_input.validate_overlay_shape(overlay_data, str(overlay_path))
    merge_result = overlay_mod.apply_overlays(base, overlay_paths)
    if not merge_result.ok:
        raise OverlayError(merge_result.violations)
    contract_errors = validate_overlay_contract(base, merge_result.merged)
    if contract_errors:
        raise InputError(
            "invalid patch-ownership overlay: " + "; ".join(contract_errors)
        )
    return merge_result.merged


def _load_answers(patch_path: str | Path, defn: dict) -> tuple[dict, dict[str, Any]]:
    from . import io_input

    input_data, input_format, row_ids = io_input.load_input(
        patch_path, "patch-ownership"
    )
    if not isinstance(input_data, dict):
        raise InputError("patch ownership input must be a mapping with 'patch' and 'answers'")
    patch_name = input_data.get("patch")
    if not isinstance(patch_name, str) or not patch_name.strip():
        raise InputError("'patch' must be a non-empty string identifier")
    input_data["patch"] = patch_name.strip()
    answers = input_data.get("answers", {}) or {}
    if not isinstance(answers, dict):
        raise InputError("'answers' must be a mapping")
    known = io_input.collect_question_ids(
        defn, non_question_groups={"gates", "examples"}
    )
    answer_ids = row_ids if input_format == "csv" else list(answers)
    io_input.validate_known_ids(answer_ids, known, Path(patch_path).name)
    return input_data, answers


def _build_context(
    base: dict, defn: dict, groups: dict, answers: dict[str, Any]
) -> tuple[dict[str, bool], list[str], dict[str, str], dict]:
    parsed = _parse_all_questions(groups, answers)
    risk_ids = [
        leaf["id"]
        for leaf in _question_leaves(groups["never_cheap"])
        if parsed[leaf["id"]]
    ]
    evidence_refs, test_status = _read_evidence(answers, bool(risk_ids))
    required_green = _required_ids(base, defn, "required_for_green")
    required_high = _required_ids(base, defn, "required_when_high_risk")
    for gid in ("probe", "ownership"):
        question_ids = [q["id"] for q in _question_leaves(groups[gid])]
        threshold = (groups[gid]["header"] or {}).get("threshold", len(question_ids))
        selected = [qid for qid in question_ids if qid in required_green]
        if len(selected) < threshold:
            extras = [qid for qid in question_ids if qid not in selected]
            required_green.update(extras[: threshold - len(selected)])
    missing_green = sorted(qid for qid in required_green if not parsed[qid])
    missing_high = sorted(qid for qid in required_high if not parsed[qid])
    if risk_ids and _REVIEW_ROUTE_REF_ID not in evidence_refs:
        missing_high.append(_REVIEW_ROUTE_REF_ID)
    ctx = {
        "test_status": test_status,
        "hollow_green_holds": _hollow_green_holds(groups, parsed),
        "risk_ids": risk_ids,
        "missing_green_requirements": missing_green,
        "missing_high_risk_controls": missing_high,
        "green_requirement_ids": required_green,
        "high_requirement_ids": required_high,
    }
    return parsed, risk_ids, evidence_refs, ctx


def _collect_missing_controls(ctx: dict) -> list[str]:
    missing = list(ctx["missing_green_requirements"])
    if ctx["risk_ids"]:
        missing += ctx["missing_high_risk_controls"]
    if not ctx["hollow_green_holds"]:
        missing.append("hollow_green")
    if ctx["test_status"] == "absent":
        missing.append("evidence.test")
    return sorted(set(missing))


def score(
    patch_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> PatchResult:
    overlay_paths = overlay_paths or []
    definition_path = definition_path or DEFAULT_DEFINITION
    from . import io_input

    base = io_input.load_yaml_unique(definition_path)
    if base.get("name") != DEFINITION_NAME:
        raise InputError(f"definition name must be '{DEFINITION_NAME}'")
    defn = merge_definition(base, overlay_paths)

    groups = overlay_mod.group_items(defn)
    if "gates" not in groups:
        raise InputError("definition is missing the 'gates' group")
    contract_errors = _threshold_contract_errors(groups)
    if contract_errors:
        raise InputError("invalid patch-ownership definition: " + "; ".join(contract_errors))

    input_data, answers = _load_answers(patch_path, defn)
    parsed, risk_ids, evidence_refs, ctx = _build_context(
        base, defn, groups, answers
    )
    sep = overlay_mod.separator_of(defn)
    region_leaf = _resolve_region(groups["gates"]["leaves"], ctx, sep)
    active = [name for name, evaluator in CONDITION_EVALUATORS.items() if evaluator(ctx)]
    ownership_required = set(ctx["green_requirement_ids"])
    if risk_ids:
        ownership_required.update(ctx["high_requirement_ids"])
    scored_groups = [
        _score_required_group(
            "probe", groups["probe"], parsed, set(ctx["green_requirement_ids"])
        ),
        _score_required_group(
            "ownership", groups["ownership"], parsed, ownership_required
        ),
        _score_hollow_group(groups["hollow_green"], parsed),
    ]
    missing_controls = _collect_missing_controls(ctx)

    return PatchResult(
        patch=input_data.get("patch") or str(patch_path),
        groups=scored_groups,
        risk_ids=risk_ids,
        missing_controls=missing_controls,
        evidence_refs=evidence_refs,
        region=region_leaf["id"],
        region_name=region_leaf.get("name_ja") or region_leaf.get("name") or region_leaf["id"],
        rationale=(region_leaf.get("action") or "").strip(),
        exit_code=int(region_leaf["exit_code"]),
        active_conditions=active,
    )


def render_text(result: PatchResult) -> str:
    lines = [f"Patch: {result.patch}", ""]
    for group in result.groups:
        lines.append(
            f"{_level_marker(group.level)} {group.id} {group.name}: "
            f"{group.level.upper()} ({group.score}/{group.threshold})"
        )
        if group.no_ids:
            lines.append(f"    no: {', '.join(group.no_ids)}")
    lines.extend([
        "",
        f"Never-cheap risks: {', '.join(result.risk_ids) if result.risk_ids else '(none)'}",
        f"Missing controls: {', '.join(result.missing_controls) if result.missing_controls else '(none)'}",
        "Evidence refs: format + digest validated; targets were not dereferenced.",
        "",
        f"Region: {result.region.upper()} — {result.region_name}",
        f"  {result.rationale}",
    ])
    return "\n".join(lines)


def render_json(result: PatchResult) -> str:
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "patch": result.patch,
            "region": result.region,
            "region_name": result.region_name,
            "exit_code": result.exit_code,
            "risk_ids": result.risk_ids,
            "missing_controls": result.missing_controls,
            "active_conditions": result.active_conditions,
            "evidence_validation": "format_and_digest_only_not_dereferenced",
            "evidence_refs": result.evidence_refs,
            "groups": [
                {
                    "id": group.id,
                    "name": group.name,
                    "level": group.level,
                    "score": group.score,
                    "threshold": group.threshold,
                    "yes": group.yes_ids,
                    "no": group.no_ids,
                }
                for group in result.groups
            ],
            "action": result.rationale,
        },
        indent=2,
        ensure_ascii=False,
    )


def _sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _sha256_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def gate_block_digest(gate: dict) -> str:
    """Digest of the gate block itself, excluding the digest field.

    ``gate_json_sha256`` ties the record back to a gate run but cannot be
    recomputed later without re-running the gate. This one can: the summary
    recomputes it and refuses a record whose gate block was edited, so the
    RED-accepted check cannot be silenced by retyping ``region``.
    """
    payload = {k: v for k, v in gate.items() if k != "block_sha256"}
    return _sha256_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    )


def build_decision_record(
    result: PatchResult,
    team: str,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
    recorded_at: str | None = None,
) -> dict:
    """Build a pending decision record from a gate result.

    The gate block is machine-transcribed on purpose. If a human retyped the
    region, a RED result could be recorded as green and the summary's
    contradiction check would never fire.
    """
    from . import io_input

    definition_path = definition_path or DEFAULT_DEFINITION
    base = io_input.load_yaml_unique(definition_path)
    if recorded_at is None:
        recorded_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
            "+00:00", "Z"
        )
    if not isinstance(team, str) or not team.strip():
        raise InputError("--team is required to emit a decision record")
    gate = {
        "region": result.region,
        "risk_ids": list(result.risk_ids),
        "missing_controls": list(result.missing_controls),
        # ``--format json`` が実際に出力するバイト列 (print の末尾改行を含む) の
        # digest。利用者が `aidr ... --format json | shasum -a 256` で照合できる。
        "gate_json_sha256": _sha256_text(render_json(result) + "\n"),
        "definition_name": str(base.get("name")),
        "definition_version": int(base.get("version", 1)),
        "overlays": [
            {"path": str(p), "sha256": _sha256_file(p)}
            for p in (overlay_paths or [])
        ],
    }
    gate["block_sha256"] = gate_block_digest(gate)
    return {
        "schema_version": SCHEMA_VERSION,
        "patch_id": result.patch,
        "team": team.strip(),
        "recorded_at": recorded_at,
        "decision": "pending",
        "gate": gate,
    }


def append_decision_record(record: dict, out_path: str | Path) -> None:
    """Append one JSON object as a line. Records are immutable events, so the
    file grows and the summary folds to the latest event per patch_id."""
    path = Path(out_path)
    if path.parent and not path.parent.exists():
        raise InputError(f"decision record directory does not exist: {path.parent}")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def render_csv_rows(result: PatchResult) -> list[list[str]]:
    from .io_input import sanitize_cell

    patch = sanitize_cell(result.patch)
    rows = [["schema_version", "record_type", "patch", "id", "name", "level", "score", "threshold", "details", "notes"]]
    for group in result.groups:
        rows.append([
            SCHEMA_VERSION, "group", patch, group.id, group.name, group.level,
            str(group.score), str(group.threshold), "; ".join(group.no_ids), "",
        ])
    rows.append([SCHEMA_VERSION, "risk", patch, "never_cheap", "", "", "", "", "; ".join(result.risk_ids), ""])
    rows.append([SCHEMA_VERSION, "summary", patch, "missing_controls", "", "", "", "", "; ".join(result.missing_controls), ""])
    rows.append([SCHEMA_VERSION, "summary", patch, "region", result.region_name, result.region, "", "", "; ".join(result.active_conditions), " ".join(result.rationale.split())])
    return rows


def _level_marker(level: str) -> str:
    return {"present": "[GREEN ]", "partial": "[YELLOW]", "absent": "[RED   ]"}.get(level, "[?     ]")
