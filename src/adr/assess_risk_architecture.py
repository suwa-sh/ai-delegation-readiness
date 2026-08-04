"""Organizational risk-architecture adequacy check (the receiving side).

Input YAML structure::

    organization: <organization/team name>
    answers:
      profile.D1_HYBRID: yes
      profile.D1_NATIVE: yes
      ...
      scenario_a.D1: yes
      scenario_a.D2: no
      ...
      owners.O1: yes
      owners.O2: yes
      owners.O3: no

Scoring model (paper: arXiv:2607.01421, "Risk Architecture for AI-Native
Engineering Teams"):

- Each capability (detection / containment / escalation) is asked as two
  MONOTONE yes/no questions — "weak-or-better capability exists" then
  "strong capability exists". no/no=0, yes/no=1, yes/yes=2; a strong=yes
  with weak=no is a contradiction (the strong capability implies the weak
  one) and fails closed as an input error.
- tau = d + c + s in {0..6}; raw band Low (tau <= 2) / Medium / High per
  the scenario header's ``medium_min`` / ``high_min``.
- The 7-dimension profile scores the same monotone way per dimension
  (0=pure-SE / 1=hybrid / 2=AI-native); the 7-value vector is primary, the
  aggregate band is a supporting view. A pure-SE band makes the scenario
  results reference-only (conclusion NOT_APPLICABLE) because the scenarios
  assume AI-native failure modes — forcing them onto a pure-SE org would
  invert the result into false BLOCKs.
- Missing surface owners cap the ``gated_by`` scenarios' effective band to
  Low (a product-specific fail-safe gate, NOT the paper's mechanism — the
  paper reflects ownership through the escalation score).

Contracts shared with ``screen_transition``:

- **Answers are mandatory (fail-closed).** A missing or ambiguous answer is
  an input error (exit 3) listing the offending ids.
- Exit codes follow the CLI-wide gate convention: 0 = every scenario High
  and all owners present (or NOT_APPLICABLE), 1 = some Medium but no Low,
  2 = any Low or a missing owner, 3 = input/overlay error.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

import overlay_scoring as overlay_mod
from .check_readiness import OverlayError
from .screen_transition import _parse_answer_strict

DEFINITION_NAME = "risk-architecture"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "risk-architecture.yaml"

_PROFILE_GROUP = "profile"
_OWNERS_GROUP = "owners"
_SCENARIO_PREFIX = "scenario_"

_CAPABILITIES = ("detection", "containment", "escalation")
_STRENGTHS = ("weak", "strong")
_DIMENSIONS = ("d1", "d2", "d3", "d4", "d5", "d6", "d7")

_BAND_LOW = "Low"
_BAND_MEDIUM = "Medium"
_BAND_HIGH = "High"

_PROFILE_PURE_SE = "pure_se"
_PROFILE_HYBRID = "hybrid"
_PROFILE_AI_NATIVE = "ai_native"


class InputError(Exception):
    """Raised when the input or the merged definition violates the contract."""


# ---------------------------------------------------------------- contract

def validate_contract(defn: dict) -> list[str]:
    """Per-definition contract the generic overlay engine cannot check.

    The engine treats leaf payload as opaque, so a syntactically valid
    overlay could add a 7th question to a scenario (breaking the {0,1,2}
    scale), a scenario group missing a capability, or a reversed band
    range. Both entry points (``assess-risk-architecture`` and
    ``check-overlay``) reject such definitions via this function.
    """
    problems: list[str] = []
    groups = overlay_mod.group_items(defn)

    for gid in groups:
        if gid not in (_PROFILE_GROUP, _OWNERS_GROUP) and not gid.startswith(_SCENARIO_PREFIX):
            problems.append(f"unknown group '{gid}' (expected profile / owners / scenario_*)")

    problems += _validate_profile(groups.get(_PROFILE_GROUP))
    problems += _validate_owners(groups.get(_OWNERS_GROUP))

    owner_leaf_ids = {
        leaf["id"] for leaf in (groups.get(_OWNERS_GROUP) or {"leaves": []})["leaves"]
    }
    scenario_gids = sorted(g for g in groups if g.startswith(_SCENARIO_PREFIX))
    if not scenario_gids:
        problems.append("at least one scenario_* group is required")
    for gid in scenario_gids:
        problems += _validate_scenario(gid, groups[gid], owner_leaf_ids)
    return problems


def _validate_texts(gid: str, leaves: list[dict]) -> list[str]:
    """Every question leaf needs non-empty ``text`` and ``text_ja``.

    The generic engine treats leaf payload as opaque, so an overlay could add
    a scenario whose questions have no Japanese text — the init template and
    the interactive skill could then render nothing. Reject at the contract.
    """
    problems: list[str] = []
    for leaf in leaves:
        for fld in ("text", "text_ja"):
            value = leaf.get(fld)
            if not isinstance(value, str) or not value.strip():
                problems.append(f"{gid}: leaf '{leaf.get('id')}' needs a non-empty {fld}")
    return problems


def _validate_monotone_pairs(
    gid: str, leaves: list[dict], key: str, expected_keys: tuple[str, ...]
) -> list[str]:
    """Every ``key`` value must appear with exactly one weak and one strong leaf."""
    problems: list[str] = []
    seen: dict[tuple[str, str], int] = {}
    for leaf in leaves:
        k = leaf.get(key)
        strength = leaf.get("strength")
        if k not in expected_keys:
            problems.append(f"{gid}: leaf '{leaf.get('id')}' has invalid {key} '{k}'")
            continue
        if strength not in _STRENGTHS:
            problems.append(f"{gid}: leaf '{leaf.get('id')}' has invalid strength '{strength}'")
            continue
        seen[(k, strength)] = seen.get((k, strength), 0) + 1
    for k in expected_keys:
        for strength in _STRENGTHS:
            n = seen.get((k, strength), 0)
            if n != 1:
                problems.append(
                    f"{gid}: expected exactly one {key}={k} strength={strength} leaf, found {n}"
                )
    return problems


def _validate_profile(group: dict | None) -> list[str]:
    if group is None or group["header"] is None:
        return ["profile group with a header is required"]
    problems: list[str] = []
    header = group["header"]
    hybrid_min = header.get("hybrid_min")
    ai_native_min = header.get("ai_native_min")
    if not _is_num(hybrid_min) or not _is_num(ai_native_min):
        problems.append("profile: hybrid_min and ai_native_min must be numeric")
    elif not (0 < hybrid_min <= ai_native_min <= 2 * len(_DIMENSIONS)):
        problems.append(
            f"profile: need 0 < hybrid_min <= ai_native_min <= {2 * len(_DIMENSIONS)} "
            f"(got hybrid_min={hybrid_min}, ai_native_min={ai_native_min})"
        )
    problems += _validate_monotone_pairs("profile", group["leaves"], "dimension", _DIMENSIONS)
    problems += _validate_texts("profile", group["leaves"])
    return problems


def _validate_owners(group: dict | None) -> list[str]:
    if group is None:
        return ["owners group is required"]
    problems: list[str] = []
    keys = [leaf.get("owner_key") for leaf in group["leaves"]]
    if len(group["leaves"]) != 3:
        problems.append(f"owners: expected exactly 3 owner questions, found {len(group['leaves'])}")
    bad = [repr(k) for k in keys if not isinstance(k, str) or not k]
    if bad:
        problems.append(f"owners: every leaf needs a non-empty owner_key (bad: {', '.join(bad)})")
    elif len(set(keys)) != len(keys):
        problems.append(f"owners: owner_key values must be unique (got: {keys})")
    problems += _validate_texts("owners", group["leaves"])
    return problems


def _validate_scenario(gid: str, group: dict, owner_leaf_ids: set[str]) -> list[str]:
    problems: list[str] = []
    header = group["header"]
    if header is None:
        return [f"{gid}: scenario group header is required"]
    medium_min = header.get("medium_min")
    high_min = header.get("high_min")
    if not _is_num(medium_min) or not _is_num(high_min):
        problems.append(f"{gid}: medium_min and high_min must be numeric")
    elif not (1 <= medium_min <= high_min <= 6):
        problems.append(
            f"{gid}: need 1 <= medium_min <= high_min <= 6 "
            f"(got medium_min={medium_min}, high_min={high_min})"
        )
    gated_by = header.get("gated_by")
    if gated_by is not None and gated_by not in owner_leaf_ids:
        problems.append(f"{gid}: gated_by '{gated_by}' does not reference an owners question")
    if len(group["leaves"]) != 6:
        problems.append(f"{gid}: expected exactly 6 questions (3 capabilities x 2), found {len(group['leaves'])}")
    problems += _validate_monotone_pairs(gid, group["leaves"], "capability", _CAPABILITIES)
    problems += _validate_texts(gid, group["leaves"])
    return problems


def _is_num(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


# ---------------------------------------------------------------- results

@dataclass
class CapabilityScore:
    capability: str
    score: int  # 0..2
    weak_id: str = ""
    strong_id: str = ""


@dataclass
class ScenarioResult:
    id: str
    name: str
    name_ja: str
    cluster: str
    capabilities: dict[str, CapabilityScore]
    tau: int
    raw_band: str
    effective_band: str
    zero_capabilities: list[str] = field(default_factory=list)
    gated_by_owner: str | None = None   # owner_key that capped this scenario, if any


@dataclass
class ProfileResult:
    dimensions: dict[str, int]  # d1..d7 -> 0..2
    total: int
    band: str  # pure_se | hybrid | ai_native


@dataclass
class OwnersResult:
    present: dict[str, bool]  # owner_key -> answered yes
    missing: list[str] = field(default_factory=list)


@dataclass
class AssessResult:
    organization: str
    profile: ProfileResult
    scenarios: list[ScenarioResult]
    owners: OwnersResult
    applicable: bool          # False => pure-SE band, scenarios are reference-only
    conclusion: str           # PASS | REVISE | BLOCK | NOT_APPLICABLE
    warnings: list[str] = field(default_factory=list)
    case_evidence: list[dict] = field(default_factory=list)


def exit_code_for(result: AssessResult) -> int:
    return {"PASS": 0, "REVISE": 1, "BLOCK": 2, "NOT_APPLICABLE": 0}[result.conclusion]


# ---------------------------------------------------------------- scoring

class _AnswerSheet:
    """Strict answer accessor that accumulates fail-closed problems."""

    def __init__(self, answers: dict):
        self.answers = answers
        self.missing: list[str] = []
        self.invalid: list[str] = []
        self.contradictions: list[str] = []

    def get(self, qid: str) -> bool | None:
        if qid not in self.answers:
            self.missing.append(qid)
            return None
        parsed = _parse_answer_strict(self.answers.get(qid))
        if parsed is None:
            self.invalid.append(f"{qid} (got: {self.answers.get(qid)!r})")
        return parsed

    def score_pair(self, weak: dict, strong: dict) -> int:
        """Monotone pair -> 0/1/2. strong=yes with weak=no is a contradiction."""
        w = self.get(weak["id"])
        s = self.get(strong["id"])
        if w is None or s is None:
            return 0  # placeholder; the sheet-level error is raised later
        if s and not w:
            self.contradictions.append(
                f"{strong['id']}=yes contradicts {weak['id']}=no "
                "(the strong capability implies the weak one)"
            )
            return 0
        return int(w) + int(s)

    def raise_if_failed(self, organization: str) -> None:
        problems = []
        if self.missing:
            problems.append(f"missing answers for: {', '.join(self.missing)}")
        if self.invalid:
            problems.append(f"invalid answers (use yes/no) for: {', '.join(self.invalid)}")
        if self.contradictions:
            problems.append(f"contradictory answers: {'; '.join(self.contradictions)}")
        if problems:
            raise InputError(f"organization '{organization}': " + "; ".join(problems))


def _pair_by(leaves: list[dict], key: str, value: str) -> tuple[dict, dict]:
    """Return the (weak, strong) leaf pair for one capability/dimension."""
    weak = next(x for x in leaves if x.get(key) == value and x.get("strength") == "weak")
    strong = next(x for x in leaves if x.get(key) == value and x.get("strength") == "strong")
    return weak, strong


def _score_profile(group: dict, sheet: _AnswerSheet) -> ProfileResult:
    header = group["header"]
    dims: dict[str, int] = {}
    for dim in _DIMENSIONS:
        weak, strong = _pair_by(group["leaves"], "dimension", dim)
        dims[dim] = sheet.score_pair(weak, strong)
    total = sum(dims.values())
    if total >= header["ai_native_min"]:
        band = _PROFILE_AI_NATIVE
    elif total >= header["hybrid_min"]:
        band = _PROFILE_HYBRID
    else:
        band = _PROFILE_PURE_SE
    return ProfileResult(dimensions=dims, total=total, band=band)


def _band_for(tau: int, header: dict) -> str:
    if tau >= header["high_min"]:
        return _BAND_HIGH
    if tau >= header["medium_min"]:
        return _BAND_MEDIUM
    return _BAND_LOW


def _score_scenario(gid: str, group: dict, sheet: _AnswerSheet) -> ScenarioResult:
    header = group["header"]
    capabilities: dict[str, CapabilityScore] = {}
    for cap in _CAPABILITIES:
        weak, strong = _pair_by(group["leaves"], "capability", cap)
        capabilities[cap] = CapabilityScore(
            capability=cap,
            score=sheet.score_pair(weak, strong),
            weak_id=weak["id"],
            strong_id=strong["id"],
        )
    tau = sum(c.score for c in capabilities.values())
    raw_band = _band_for(tau, header)
    return ScenarioResult(
        id=gid,
        name=header.get("name", gid),
        name_ja=header.get("name_ja", gid),
        cluster=str(header.get("cluster", "")),
        capabilities=capabilities,
        tau=tau,
        raw_band=raw_band,
        effective_band=raw_band,
        zero_capabilities=[c.capability for c in capabilities.values() if c.score == 0],
    )


def _score_owners(group: dict, sheet: _AnswerSheet) -> OwnersResult:
    present: dict[str, bool] = {}
    for leaf in group["leaves"]:
        ans = sheet.get(leaf["id"])
        present[leaf["owner_key"]] = bool(ans)
    missing = [k for k, v in present.items() if not v]
    return OwnersResult(present=present, missing=missing)


def _apply_owner_gate(
    scenarios: list[ScenarioResult],
    groups: dict,
    owners_group: dict,
    owners: OwnersResult,
) -> None:
    """Cap gated scenarios to Low when their surface owner is absent.

    Product-specific fail-safe gate (see module docstring), applied only
    when the profile makes the scenarios applicable.
    """
    owner_key_by_leaf = {leaf["id"]: leaf["owner_key"] for leaf in owners_group["leaves"]}
    for s in scenarios:
        gated_by = (groups[s.id]["header"] or {}).get("gated_by")
        if gated_by is None:
            continue
        owner_key = owner_key_by_leaf[gated_by]
        if not owners.present.get(owner_key, False):
            s.effective_band = _BAND_LOW
            s.gated_by_owner = owner_key


def _conclude(result_scenarios: list[ScenarioResult], owners: OwnersResult) -> str:
    if owners.missing or any(s.effective_band == _BAND_LOW for s in result_scenarios):
        return "BLOCK"
    if any(s.effective_band == _BAND_MEDIUM for s in result_scenarios):
        return "REVISE"
    return "PASS"


def _boundary_warnings(scenarios: list[ScenarioResult]) -> list[str]:
    """Name the specific uncovered boundary scenarios (never the whole cluster)."""
    warnings = []
    for s in scenarios:
        if s.cluster == "F" and s.effective_band == _BAND_LOW:
            reason = (
                f"capped by missing {s.gated_by_owner}"
                if s.gated_by_owner
                else f"zero capabilities: {', '.join(s.zero_capabilities) or 'none'}"
            )
            warnings.append(
                f"boundary failure '{s.id}' ({s.name_ja}) is uncovered ({reason}) — "
                "the paper identifies dependency-boundary failures as the least covered "
                "category; this statement applies to this scored scenario only"
            )
    return warnings


# ---------------------------------------------------------------- loading

def validate_overlay_files(overlay_paths: list[str | Path]) -> None:
    """Pre-validate overlay files with the strict loader before merging.

    ``check-overlay`` rejects duplicate YAML keys via ``load_yaml_unique``,
    but the generic ``apply_overlays`` re-loads with plain ``safe_load``
    (last key wins). Without this pre-pass the same overlay would fail the
    pre-check yet silently score with the losing value at run time.
    """
    from . import io_input

    for path in overlay_paths:
        try:
            overlay = io_input.load_yaml_unique(path)
        except yaml.YAMLError as e:
            raise InputError(f"overlay {path} is not valid YAML: {e}") from e
        io_input.validate_overlay_shape(overlay, str(path))


def _resolve_definition(
    overlay_paths: list[str | Path],
    definition_path: str | Path | None,
) -> dict:
    base = overlay_mod.load_yaml(definition_path or DEFAULT_DEFINITION)
    if not overlay_paths:
        return base
    validate_overlay_files(overlay_paths)
    result = overlay_mod.apply_overlays(base, overlay_paths)
    if not result.ok:
        raise OverlayError(result.violations)
    return result.merged


def _load_answers(business_path: str | Path, defn: dict) -> tuple[str, dict]:
    from . import io_input

    try:
        input_data, input_format, row_ids = io_input.load_input(business_path, "risk-architecture")
    except yaml.YAMLError as e:
        raise InputError(f"input is not valid YAML: {e}") from e
    if input_format == "csv":
        known = io_input.collect_question_ids(defn, non_question_groups=set())
        io_input.validate_known_ids(row_ids, known, Path(business_path).name)
    if not isinstance(input_data, dict):
        raise InputError("input must be a YAML mapping with 'organization' and 'answers'")
    organization = input_data.get("organization")
    if not organization:
        raise InputError("input must name the 'organization' being assessed")
    answers = input_data.get("answers")
    if not isinstance(answers, dict):
        raise InputError("'answers' must be a mapping of question id -> yes/no")
    return str(organization), answers


# ---------------------------------------------------------------- assess

def assess(
    business_path: str | Path,
    overlay_paths: list[str | Path] | None = None,
    definition_path: str | Path | None = None,
) -> AssessResult:
    defn = _resolve_definition(overlay_paths or [], definition_path)
    contract_problems = validate_contract(defn)
    if contract_problems:
        raise InputError(
            "definition violates the risk-architecture contract: "
            + "; ".join(contract_problems)
        )

    groups = overlay_mod.group_items(defn)
    organization, answers = _load_answers(business_path, defn)

    sheet = _AnswerSheet(answers)
    profile = _score_profile(groups[_PROFILE_GROUP], sheet)
    scenario_gids = [g for g in groups if g.startswith(_SCENARIO_PREFIX)]
    scenarios = [_score_scenario(gid, groups[gid], sheet) for gid in scenario_gids]
    owners = _score_owners(groups[_OWNERS_GROUP], sheet)
    sheet.raise_if_failed(organization)

    # Applicability: the aggregate band alone would let a team with full
    # multi-step autonomy (D2=2) but low totals slip out of the gate — D2 is
    # the paper's strongest profile-transition signal. D2=1 (AI recommends,
    # humans approve the irreversible actions) is NOT enough on its own: the
    # scenarios presuppose autonomous multi-step execution, and forcing them
    # onto a human-approval org would produce false BLOCKs.
    applicable = profile.band != _PROFILE_PURE_SE or profile.dimensions["d2"] >= 2
    warnings: list[str] = []
    if applicable:
        _apply_owner_gate(scenarios, groups, groups[_OWNERS_GROUP], owners)
        conclusion = _conclude(scenarios, owners)
        warnings = _boundary_warnings(scenarios)
        if profile.band == _PROFILE_PURE_SE:
            warnings.append(
                "profile band is pure-SE but D2=2 (agents execute multi-step sequences "
                "without per-action approval) — the gate stays on because that autonomy "
                "alone activates the agentic failure modes"
            )
    else:
        conclusion = "NOT_APPLICABLE"
        warnings.append(
            "profile band is pure-SE without autonomous multi-step execution (D2<2): "
            "the scenarios assume AI-native failure modes, so their scores are "
            "reference-only and no gate is applied (re-assess when agents start "
            "acting without per-action approval)"
        )

    # Scenarios render worst-first so the reader sees the gaps immediately.
    band_order = {_BAND_LOW: 0, _BAND_MEDIUM: 1, _BAND_HIGH: 2}
    scenarios.sort(key=lambda s: (band_order[s.effective_band], s.tau, s.id))

    # Aggregate profile + owners evidence so the JSON carries every caveat the
    # interactive skill must quote (incl. the derived-counterfactual and RACI
    # notes on the owners header) — not just the profile thresholds.
    case_evidence = [
        *((groups[_PROFILE_GROUP]["header"] or {}).get("case_evidence", []) or []),
        *((groups[_OWNERS_GROUP]["header"] or {}).get("case_evidence", []) or []),
    ]
    return AssessResult(
        organization=organization,
        profile=profile,
        scenarios=scenarios,
        owners=owners,
        applicable=applicable,
        conclusion=conclusion,
        warnings=warnings,
        case_evidence=case_evidence,
    )


# ---------------------------------------------------------------- render

_BAND_MARKERS = {_BAND_LOW: "[LOW   ]", _BAND_MEDIUM: "[MEDIUM]", _BAND_HIGH: "[HIGH  ]"}


def render_text(result: AssessResult) -> str:
    lines = [f"organization: {result.organization}"]
    dims = " ".join(f"{d.upper()}={v}" for d, v in result.profile.dimensions.items())
    lines.append(
        f"profile: {dims}  total={result.profile.total}  band={result.profile.band}"
    )
    if not result.applicable:
        lines.append("scenarios (reference only — profile band is pure-SE):")
    else:
        lines.append("scenarios:")
    for s in result.scenarios:
        caps = " ".join(f"{c.capability[0]}={c.score}" for c in s.capabilities.values())
        gate = f"  (capped: {s.gated_by_owner} missing)" if s.gated_by_owner else ""
        zero = (
            f"  zero: {', '.join(s.zero_capabilities)}"
            if s.effective_band == _BAND_LOW and s.zero_capabilities
            else ""
        )
        lines.append(
            f"{_BAND_MARKERS[s.effective_band]} {s.id} ({s.name_ja}): "
            f"tau={s.tau} ({caps}) raw={s.raw_band} effective={s.effective_band}{gate}{zero}"
        )
    owner_summary = " ".join(
        f"{k}={'yes' if v else 'NO'}" for k, v in result.owners.present.items()
    )
    lines.append(f"owners: {owner_summary}")
    for w in result.warnings:
        lines.append(f"warning: {w}")
    lines.append(f"conclusion: {result.conclusion}")
    lines.append("")
    lines.append(
        "Note: a representative-scenario quick check, not the paper's full scoring. "
        "The claim that owner assignment removes Low bands is the author's derived "
        "counterfactual, not a measurement — verify against your own incidents."
    )
    return "\n".join(lines)


def render_csv_rows(result: AssessResult) -> list[list[str]]:
    from .io_input import sanitize_cell

    rows = [[
        "record_type", "organization", "id", "name_ja", "cluster",
        "detection", "containment", "escalation", "tau",
        "raw_band", "effective_band", "capped_by_missing_owner",
    ]]
    org = sanitize_cell(result.organization)
    for s in result.scenarios:
        rows.append([
            "scenario", org, s.id, sanitize_cell(s.name_ja), s.cluster,
            str(s.capabilities["detection"].score),
            str(s.capabilities["containment"].score),
            str(s.capabilities["escalation"].score),
            str(s.tau), s.raw_band, s.effective_band, s.gated_by_owner or "",
        ])
    for dim, v in result.profile.dimensions.items():
        rows.append(["profile_dimension", org, dim, "", "", "", "", "", str(v), "", "", ""])
    rows.append([
        "summary", org, "profile_band", result.profile.band, "",
        "", "", "", str(result.profile.total), "", "", "",
    ])
    for k, v in result.owners.present.items():
        rows.append(["owner", org, k, "", "", "", "", "", "", "", "", "present" if v else "missing"])
    rows.append(["summary", org, "conclusion", result.conclusion, "", "", "", "", "", "", "", ""])
    return rows


def render_json(result: AssessResult) -> str:
    payload = {
        "organization": result.organization,
        "profile": {
            "dimensions": result.profile.dimensions,
            "total": result.profile.total,
            "band": result.profile.band,
        },
        "applicable": result.applicable,
        "scenarios": [
            {
                "id": s.id,
                "name": s.name,
                "name_ja": s.name_ja,
                "cluster": s.cluster,
                "capabilities": {c.capability: c.score for c in s.capabilities.values()},
                "tau": s.tau,
                "raw_band": s.raw_band,
                "effective_band": s.effective_band,
                "zero_capabilities": s.zero_capabilities,
                "capped_by_missing_owner": s.gated_by_owner,
            }
            for s in result.scenarios
        ],
        "owners": {"present": result.owners.present, "missing": result.owners.missing},
        "warnings": result.warnings,
        "conclusion": result.conclusion,
        # Source notes with confidence labels (incl. the derived-counterfactual
        # and design_proposal caveats) for client-facing traceability.
        "case_evidence": result.case_evidence,
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)
