"""Summarize patch decision records into a monthly retrospective.

The gate (``check-patch-ownership``) judges one patch. This module reads the
records of what humans then did with those patches and reports:

- the discard rate over *decided* patches,
- the decided rate, so a pile of pending records cannot flatter the rate,
- the discard-reason mix, so the number implies an action,
- accepted patches whose gate verdict was RED, which is a contradiction that
  needs no threshold to detect.

The denominator is limited to patches that went through the gate and produced a
record. Patches discarded without ever running the gate cannot be observed, so
the reported figure is the discard rate of *gated* patches only.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import overlay_scoring as overlay_mod
from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

DEFINITION_NAME = "patch-decision"
DEFAULT_DEFINITION = Path(__file__).resolve().parents[2] / "definitions" / "patch-decision.yaml"
DEFAULT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "patch-decision.schema.json"

SCHEMA_VERSION = "1"
_REASON_GROUP = "discard_reason"
_BANDS_GROUP = "bands"
_DECIDED = ("accepted", "discarded")
_BAND_REQUIRED = ("applies_to", "low", "high", "label", "label_ja")
_BAND_METRICS = ("discard_rate",)
_PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_RECORD_SUFFIXES = (".jsonl", ".json")


class InputError(Exception):
    """Malformed input, definition, or overlay. Always surfaces as exit 3."""


class OverlayError(Exception):
    def __init__(self, violations):
        self.violations = violations
        super().__init__("; ".join(str(v) for v in violations))


@dataclass
class Band:
    id: str
    low: float
    high: float
    label: str
    label_ja: str

    def contains(self, value: float) -> bool:
        """Half-open so adjacent bands cannot both claim a boundary value."""
        return self.low <= value < self.high


@dataclass
class DecisionSummary:
    team: str
    period: str
    record_count: int
    patch_count: int
    accepted: int
    discarded: int
    pending: int
    reason_counts: dict[str, int] = field(default_factory=dict)
    red_accepted: list[str] = field(default_factory=list)
    yellow_accepted: list[str] = field(default_factory=list)
    bands: list[Band] = field(default_factory=list)

    @property
    def decided(self) -> int:
        return self.accepted + self.discarded

    @property
    def discard_rate(self) -> float | None:
        """None when nothing is decided yet — never 0.0, which reads as 'nobody discards'."""
        return (self.discarded / self.decided) if self.decided else None

    @property
    def decided_rate(self) -> float | None:
        return (self.decided / self.patch_count) if self.patch_count else None

    @property
    def matched_band(self) -> Band | None:
        rate = self.discard_rate
        if rate is None:
            return None
        for band in self.bands:
            if band.contains(rate):
                return band
        return None

    @property
    def exit_code(self) -> int:
        if self.red_accepted:
            return 2
        if self.pending:
            return 1
        return 0


def _build_validator(schema_path: Path) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    schema_id = schema.get("$id", str(schema_path))
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    registry: Registry = Registry().with_resource(schema_id, resource)
    # format_checker がないと "date-time" / "date" は no-op になり、
    # recorded_at に任意文字列が通って fold の順序が壊れる。
    return Draft202012Validator(
        schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def _iter_file_sources(path: Path) -> Iterator[tuple[str, str]]:
    """Yield (origin, raw_json) without holding the whole file as one list.

    ``.jsonl`` is one record per line; ``.json`` is a single object. A month-per-
    file directory (decisions/2026-07.jsonl) is the documented layout, so both
    suffixes must work for a directory as well as a direct path.
    """
    if path.suffix == ".json":
        yield str(path), path.read_text(encoding="utf-8")
        return
    with path.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, start=1):
            if line.strip():
                yield f"{path}:{lineno}", line


def _iter_record_sources(path: Path) -> Iterator[tuple[str, str]]:
    if path.is_dir():
        files = sorted(
            p for p in path.iterdir() if p.is_file() and p.suffix in _RECORD_SUFFIXES
        )
        if not files:
            raise InputError(
                f"no *.jsonl or *.json records found in directory: {path}"
            )
        for file_path in files:
            yield from _iter_file_sources(file_path)
        return
    if not path.exists():
        raise InputError(f"input not found: {path}")
    yield from _iter_file_sources(path)


def _verify_gate_block(record: dict, origin: str) -> None:
    from .check_patch_ownership import gate_block_digest

    gate = record["gate"]
    expected = gate_block_digest(gate)
    if gate["block_sha256"] != expected:
        raise InputError(
            f"{origin}: gate block digest mismatch for patch '{record['patch_id']}'. "
            "The gate block is machine-generated; edit only decision, decided_on, "
            "discard_reason and note."
        )


def _load_records(path: Path, schema_path: Path) -> list[dict]:
    validator = _build_validator(schema_path)
    records: list[dict] = []
    for origin, raw in _iter_record_sources(path):
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise InputError(f"{origin}: invalid JSON: {e}") from e
        if not isinstance(data, dict):
            raise InputError(f"{origin}: record must be a JSON object")
        errors = sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path))
        if errors:
            first = errors[0]
            location = "/" + "/".join(str(p) for p in first.absolute_path)
            raise InputError(f"{origin}: schema violation at {location}: {first.message}")
        _verify_gate_block(data, origin)
        records.append(data)
    return records


def _resolve_definition(overlay_paths: list[str | Path]) -> dict:
    from . import io_input

    base = io_input.load_yaml_unique(DEFAULT_DEFINITION)
    if base.get("name") != DEFINITION_NAME:
        raise InputError(f"definition name must be '{DEFINITION_NAME}'")
    if not overlay_paths:
        return base
    for overlay_path in overlay_paths:
        overlay_data = io_input.load_yaml_unique(overlay_path)
        io_input.validate_overlay_shape(overlay_data, str(overlay_path))
    merge_result = overlay_mod.apply_overlays(base, overlay_paths)
    if not merge_result.ok:
        raise OverlayError(merge_result.violations)
    return merge_result.merged


def declared_reason_ids(defn: dict) -> set[str]:
    """Leaf names of the discard_reason group, without the group prefix."""
    sep = overlay_mod.separator_of(defn)
    group = overlay_mod.group_items(defn).get(_REASON_GROUP)
    if not group:
        raise InputError(f"definition is missing the '{_REASON_GROUP}' group")
    return {leaf["id"].split(sep, 1)[1] for leaf in group["leaves"]}


def _band_contract_error(leaf: dict, sep: str) -> str | None:
    leaf_id = leaf["id"]
    missing = [f for f in _BAND_REQUIRED if leaf.get(f) in (None, "")]
    if missing:
        return f"{leaf_id}: missing required band fields: {', '.join(missing)}"
    if leaf["applies_to"] not in _BAND_METRICS:
        return (
            f"{leaf_id}: applies_to must be one of {', '.join(_BAND_METRICS)}; "
            f"got '{leaf['applies_to']}'"
        )
    bounds = {}
    for name in ("low", "high"):
        raw = leaf[name]
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return f"{leaf_id}: {name} must be a number between 0.0 and 1.0"
        value = float(raw)
        if not 0.0 <= value <= 1.0:
            return f"{leaf_id}: {name} must be between 0.0 and 1.0; got {value}"
        bounds[name] = value
    if bounds["low"] >= bounds["high"]:
        return f"{leaf_id}: low must be strictly less than high"
    _ = sep
    return None


def load_bands(defn: dict) -> list[Band]:
    """Read and validate bands. The merge engine treats payload as opaque, so
    an organization's overlay can inject a malformed band; this is where it stops."""
    sep = overlay_mod.separator_of(defn)
    group = overlay_mod.group_items(defn).get(_BANDS_GROUP)
    if not group:
        return []
    bands: list[Band] = []
    for leaf in group["leaves"]:
        error = _band_contract_error(leaf, sep)
        if error:
            raise InputError(f"invalid patch-decision band: {error}")
        bands.append(
            Band(
                id=leaf["id"].split(sep, 1)[1],
                low=float(leaf["low"]),
                high=float(leaf["high"]),
                label=str(leaf["label"]),
                label_ja=str(leaf["label_ja"]),
            )
        )
    ordered = sorted(bands, key=lambda b: b.low)
    for earlier, later in zip(ordered, ordered[1:]):
        if later.low < earlier.high:
            raise InputError(
                f"invalid patch-decision band: {earlier.id} and {later.id} overlap "
                f"([{earlier.low}, {earlier.high}) vs [{later.low}, {later.high}))"
            )
    return ordered


def _period_of(record: dict) -> str:
    """Pending records have no decided_on, so they bucket by when they were recorded."""
    stamp = record.get("decided_on") or record["recorded_at"]
    return str(stamp)[:7]


def _recorded_at(record: dict) -> datetime:
    """Parse to an aware UTC instant.

    String comparison would order '2026-07-31T23:30:00-05:00' before
    '2026-08-01T03:00:00Z' even though it is the later instant, which would
    fold to the wrong event and could hide a RED-accepted decision.
    """
    raw = record["recorded_at"]
    parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _decision_key(record: dict) -> tuple:
    return (record["decision"], record.get("discard_reason"), record.get("decided_on"))


def fold_latest(records: list[dict]) -> list[dict]:
    """Keep the latest event per patch_id.

    Appending 'pending' and later 'accepted' for the same patch is the normal
    workflow; without this fold the patch would be counted twice. Two events
    with the same instant but different outcomes are an input error: picking
    one by file order would silently decide whether a contradiction is
    reported.
    """
    latest: dict[str, tuple[datetime, dict]] = {}
    for record in records:
        key = record["patch_id"]
        stamp = _recorded_at(record)
        current = latest.get(key)
        if current is None or stamp > current[0]:
            latest[key] = (stamp, record)
        elif stamp == current[0] and _decision_key(record) != _decision_key(current[1]):
            raise InputError(
                f"patch '{key}' has two different outcomes at the same recorded_at "
                f"({record['recorded_at']}); give the later event a later timestamp"
            )
    return [record for _, record in latest.values()]


def _reject_undeclared_reasons(records: list[dict], declared: set[str]) -> None:
    for record in records:
        reason = record.get("discard_reason")
        if reason is not None and reason not in declared:
            raise InputError(
                f"unknown discard_reason '{reason}' for patch '{record['patch_id']}'; "
                f"declared reasons are: {', '.join(sorted(declared))}"
            )


@dataclass
class _Tally:
    counts: dict[str, int]
    reason_counts: dict[str, int]
    red_accepted: list[str]
    yellow_accepted: list[str]


def _tally(folded: list[dict]) -> _Tally:
    counts = {"accepted": 0, "discarded": 0, "pending": 0}
    reason_counts: dict[str, int] = {}
    accepted_by_region: dict[str, list[str]] = {"red": [], "yellow": []}
    for record in folded:
        decision = record["decision"]
        counts[decision] += 1
        if decision == "discarded":
            reason = record["discard_reason"]
            reason_counts[reason] = reason_counts.get(reason, 0) + 1
        elif decision == "accepted":
            bucket = accepted_by_region.get(record["gate"]["region"])
            if bucket is not None:
                bucket.append(record["patch_id"])
    return _Tally(
        counts=counts,
        reason_counts=reason_counts,
        red_accepted=sorted(accepted_by_region["red"]),
        yellow_accepted=sorted(accepted_by_region["yellow"]),
    )


def _filter_records(
    records: list[dict], period: str | None, team: str | None
) -> list[dict]:
    if team:
        records = [r for r in records if r["team"] == team]
    if period:
        records = [r for r in records if _period_of(r) == period]
    return records


def summarize(
    path: str | Path,
    period: str | None = None,
    team: str | None = None,
    overlay_paths: list[str | Path] | None = None,
    schema_path: str | Path | None = None,
) -> DecisionSummary:
    overlay_paths = list(overlay_paths or [])
    if period is not None and not _PERIOD_PATTERN.match(period):
        # 未検証だと typo が「0 件・exit 0」に化け、RED 採用を含む月が
        # 素通りしたことに気づけない。
        raise InputError(f"--period must be YYYY-MM (month 01-12); got '{period}'")
    defn = _resolve_definition(overlay_paths)
    bands = load_bands(defn)

    records = _load_records(Path(path), Path(schema_path or DEFAULT_SCHEMA))
    _reject_undeclared_reasons(records, declared_reason_ids(defn))

    # fold してから絞り込む。逆順にすると、翌月に決着したパッチが前月の
    # レポートで未決のまま残り、latest-wins の契約と食い違う。
    folded = _filter_records(fold_latest(records), period, team)
    tally = _tally(folded)

    teams = sorted({r["team"] for r in folded})
    periods = sorted({_period_of(r) for r in folded})
    return DecisionSummary(
        team=team or (teams[0] if len(teams) == 1 else f"{len(teams)} teams"),
        period=period or _period_span(periods),
        record_count=len(records),
        patch_count=len(folded),
        accepted=tally.counts["accepted"],
        discarded=tally.counts["discarded"],
        pending=tally.counts["pending"],
        reason_counts=tally.reason_counts,
        red_accepted=tally.red_accepted,
        yellow_accepted=tally.yellow_accepted,
        bands=bands,
    )


def _period_span(periods: list[str]) -> str:
    if not periods:
        return "(no records)"
    return periods[0] if len(periods) == 1 else f"{periods[0]}..{periods[-1]}"


def _pct(value: float | None) -> str:
    return "N/A" if value is None else f"{value * 100:.1f}%"


def render_text(result: DecisionSummary) -> str:
    lines = [
        f"Team: {result.team}",
        f"Period: {result.period}",
        f"Records read: {result.record_count} -> {result.patch_count} patches in scope "
        f"(repeated events for one patch fold to its latest)",
        "",
    ]
    if result.patch_count == 0:
        lines.append("No records matched. Nothing to summarize.")
        return "\n".join(lines)

    lines.extend([
        f"Discard rate (gated patches): {_pct(result.discard_rate)}"
        f"  = {result.discarded} discarded / {result.decided} decided",
        f"Decided rate: {_pct(result.decided_rate)}"
        f"  = {result.decided} decided / {result.patch_count} patches",
        f"Undecided: {result.pending} patch(es)",
    ])
    if result.discard_rate is None:
        lines.append("  Nothing has been decided yet, so no rate can be computed.")

    band = result.matched_band
    if result.bands:
        if band:
            lines.append(f"Band: {band.label_ja} [{band.low}, {band.high})")
        elif result.discard_rate is not None:
            lines.append("Band: no configured band covers this rate")
    else:
        lines.append(
            "Band: not configured — this tool ships no numeric healthy range. "
            "See docs/12 to set your own baseline by overlay."
        )

    lines.extend(["", "Discard reasons:"])
    if result.discarded:
        for reason, count in sorted(
            result.reason_counts.items(), key=lambda kv: (-kv[1], kv[0])
        ):
            share = count / result.discarded
            lines.append(f"  {reason}: {count} ({share * 100:.1f}% of discards)")
    else:
        lines.append("  (no discarded patches)")

    lines.extend(["", "Gate cross-check:"])
    if result.red_accepted:
        lines.append(
            f"  [NG] RED accepted: {len(result.red_accepted)} "
            f"({', '.join(result.red_accepted)})"
        )
        lines.append(
            "       RED means 'do not accept'. Accepting it contradicts the gate."
        )
    else:
        lines.append("  [OK] RED accepted: 0")
    lines.append(
        f"  [..] YELLOW accepted: {len(result.yellow_accepted)} "
        "(a human decision was required; this is the designed path)"
    )

    lines.extend([
        "",
        "How to read this:",
        "  High discard rate  -> probes may be produced faster than they can be judged.",
        "  Low discard rate   -> a working patch may be accepted by default (sunk cost).",
        "  Low decided rate   -> the rate comes from a small decided subset; read it later.",
        "",
        "Coverage limit: the denominator is patches that went through the gate and",
        "produced a record. Patches discarded without running the gate never appear here.",
    ])
    return "\n".join(lines)


def render_json(result: DecisionSummary) -> str:
    band = result.matched_band
    return json.dumps(
        {
            "schema_version": SCHEMA_VERSION,
            "team": result.team,
            "period": result.period,
            "record_count": result.record_count,
            "patch_count": result.patch_count,
            "accepted": result.accepted,
            "discarded": result.discarded,
            "pending": result.pending,
            "decided": result.decided,
            "discard_rate": result.discard_rate,
            "decided_rate": result.decided_rate,
            "discard_reasons": [
                {
                    "id": reason,
                    "count": count,
                    "share_of_discards": count / result.discarded,
                }
                for reason, count in sorted(
                    result.reason_counts.items(), key=lambda kv: (-kv[1], kv[0])
                )
            ],
            "red_accepted": result.red_accepted,
            "yellow_accepted": result.yellow_accepted,
            "band": None if band is None else {"id": band.id, "low": band.low, "high": band.high},
            "band_configured": bool(result.bands),
            "coverage": "gated_patches_with_a_record_only",
            "exit_code": result.exit_code,
        },
        indent=2,
        ensure_ascii=False,
    )


def render_csv_rows(result: DecisionSummary) -> list[list[str]]:
    from .io_input import sanitize_cell

    rows = [["record_type", "id", "count", "share", "note"]]
    rows.append(["summary", "team", "", "", sanitize_cell(result.team)])
    rows.append(["summary", "period", "", "", sanitize_cell(result.period)])
    rows.append(["summary", "patches", str(result.patch_count), "", ""])
    rows.append(["summary", "accepted", str(result.accepted), "", ""])
    rows.append(["summary", "discarded", str(result.discarded), "", ""])
    rows.append(["summary", "pending", str(result.pending), "", ""])
    rows.append(["metric", "discard_rate", "", _pct(result.discard_rate), "of decided patches"])
    rows.append(["metric", "decided_rate", "", _pct(result.decided_rate), "of gated patches"])
    for reason, count in sorted(result.reason_counts.items(), key=lambda kv: (-kv[1], kv[0])):
        share = count / result.discarded
        rows.append(["discard_reason", reason, str(count), f"{share * 100:.1f}%", ""])
    rows.append([
        "gate_crosscheck",
        "red_accepted",
        str(len(result.red_accepted)),
        "",
        sanitize_cell(", ".join(result.red_accepted)),
    ])
    rows.append([
        "gate_crosscheck",
        "yellow_accepted",
        str(len(result.yellow_accepted)),
        "",
        sanitize_cell(", ".join(result.yellow_accepted)),
    ])
    rows.append([
        "coverage",
        "denominator",
        "",
        "",
        "gated patches with a record only; ungated discards are not observable",
    ])
    return rows


def exit_code_for(result: DecisionSummary) -> int:
    return result.exit_code
