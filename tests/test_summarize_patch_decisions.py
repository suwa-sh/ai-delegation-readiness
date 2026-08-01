"""Monthly retrospective tests for recorded patch decisions.

Pins the invariants that make the discard rate trustworthy: pending records
must not leak into the denominator, the rate must read as "unknown" rather
than a false zero when nothing is decided, and repeated events for one patch
must fold to a single, latest-wins outcome.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import overlay_scoring as ov
from adr import summarize_patch_decisions as sd
from conftest import (
    patch_decision_path,
    patch_decision_team_bands_overlay_path,
    sample_patch_decisions_demo_path,
    sample_patch_decisions_midori_path,
)

GATE_GREEN = {
    "region": "green",
    "risk_ids": [],
    "missing_controls": [],
    "gate_json_sha256": "a" * 64,
    "definition_name": "patch-ownership",
    "definition_version": 1,
    "overlays": [],
}

GATE_RED = {**GATE_GREEN, "region": "red"}


def _record(
    patch_id: str,
    decision: str,
    recorded_at: str,
    team: str = "team-a",
    decided_on: str | None = None,
    discard_reason: str | None = None,
    gate: dict | None = None,
) -> dict:
    record = {
        "schema_version": "1",
        "patch_id": patch_id,
        "team": team,
        "recorded_at": recorded_at,
        "decision": decision,
        "gate": dict(gate or GATE_GREEN),
    }
    if decided_on is not None:
        record["decided_on"] = decided_on
    if discard_reason is not None:
        record["discard_reason"] = discard_reason
    return record


def _write_jsonl(tmp_path: Path, records: list[dict], name: str = "decisions.jsonl") -> Path:
    path = tmp_path / name
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


def _accepted(patch_id: str, day: str) -> dict:
    return _record(patch_id, "accepted", f"2026-07-{day}T09:00:00Z", decided_on=f"2026-07-{day}")


def _discarded(patch_id: str, day: str, reason: str) -> dict:
    return _record(
        patch_id, "discarded", f"2026-07-{day}T09:00:00Z",
        decided_on=f"2026-07-{day}", discard_reason=reason,
    )


def _pending(patch_id: str, day: str) -> dict:
    return _record(patch_id, "pending", f"2026-07-{day}T09:00:00Z")


# --- fold_latest --------------------------------------------------------

def test_fold_latest_同一patch_idが複数回記録された場合_最新recorded_atの1件に畳まれること():
    # Arrange
    records = [_pending("p1", "01"), _accepted("p1", "10")]

    # Act
    folded = sd.fold_latest(records)

    # Assert
    assert len(folded) == 1
    assert folded[0]["decision"] == "accepted"


def test_fold_latest_異なるpatch_idの場合_両方が残ること():
    # Arrange
    records = [_accepted("p1", "01"), _discarded("p2", "02", "cost_not_worth")]

    # Act
    folded = sd.fold_latest(records)

    # Assert
    assert {r["patch_id"] for r in folded} == {"p1", "p2"}


# --- summarize: discard rate excludes pending ----------------------------

def test_summarize_pendingを追加した場合_discard_rateが変化しないこと(tmp_path):
    # Arrange
    base = [
        _accepted("p1", "01"),
        _accepted("p2", "02"),
        _discarded("p3", "03", "cost_not_worth"),
    ]
    with_pending = base + [_pending("p4", "04")]

    # Act
    base_result = sd.summarize(_write_jsonl(tmp_path, base, "base.jsonl"))
    with_pending_result = sd.summarize(_write_jsonl(tmp_path, with_pending, "with_pending.jsonl"))

    # Assert
    assert base_result.discard_rate == with_pending_result.discard_rate == pytest.approx(1 / 3)


def test_summarize_decided_rateの場合_decided割るpatch_countであること(tmp_path):
    # Arrange
    records = [
        _accepted("p1", "01"),
        _discarded("p2", "02", "cost_not_worth"),
        _pending("p3", "03"),
    ]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))

    # Assert
    assert result.decided == 2
    assert result.decided_rate == pytest.approx(2 / 3)


def test_summarize_何も決定されていない場合_discard_rateがNoneであること(tmp_path):
    # Arrange
    records = [_pending("p1", "01"), _pending("p2", "02")]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))

    # Assert
    assert result.discard_rate is None


def test_render_text_discard_rateがNoneの場合_N_Aと表示されること(tmp_path):
    # Arrange
    records = [_pending("p1", "01")]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))
    text = sd.render_text(result)

    # Assert
    discard_line = next(line for line in text.splitlines() if line.startswith("Discard rate"))
    assert "N/A" in discard_line
    assert "0.0%" not in discard_line


def test_summarize_reason_sharesの場合_discard件数に対して100パーセントになること(tmp_path):
    # Arrange
    records = [
        _accepted("p1", "01"),
        _discarded("p2", "02", "cost_not_worth"),
        _discarded("p3", "03", "cost_not_worth"),
        _discarded("p4", "04", "probe_oversized"),
    ]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))
    total_share = sum(count / result.discarded for count in result.reason_counts.values())

    # Assert
    assert total_share == pytest.approx(1.0)
    assert result.reason_counts == {"cost_not_worth": 2, "probe_oversized": 1}


# --- latest-wins fold changes the decision -------------------------------

def test_summarize_pendingの後にacceptedが記録された場合_1patchとしてacceptedにカウントされること(tmp_path):
    # Arrange
    records = [_pending("p1", "01"), _accepted("p1", "20")]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))

    # Assert
    assert result.patch_count == 1
    assert result.accepted == 1
    assert result.pending == 0


# --- exit codes ------------------------------------------------------------

@pytest.mark.parametrize(
    ("records", "expected_exit"),
    [
        pytest.param(
            [_record("p1", "accepted", "2026-07-01T00:00:00Z", decided_on="2026-07-01", gate=GATE_RED)],
            2,
            id="red_acceptedがある場合_exit2になること",
        ),
        pytest.param(
            [_pending("p1", "01")],
            1,
            id="pendingのみの場合_exit1になること",
        ),
        pytest.param(
            [_accepted("p1", "01")],
            0,
            id="全て決定済みでredもない場合_exit0になること",
        ),
        pytest.param(
            [
                _record("p1", "accepted", "2026-07-01T00:00:00Z", decided_on="2026-07-01", gate=GATE_RED),
                _pending("p2", "02"),
            ],
            2,
            id="red_acceptedとpendingが両方ある場合_exit2が優先されること",
        ),
    ],
)
def test_summarize_exit_codeの場合_gate結果とpendingの組み合わせに従うこと(tmp_path, records, expected_exit):
    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records))

    # Assert
    assert result.exit_code == expected_exit


# --- team / period filters --------------------------------------------------

def test_summarize_teamで絞り込んだ場合_該当teamのみ集計されること(tmp_path):
    # Arrange
    records = [
        _record("p1", "accepted", "2026-07-01T00:00:00Z", team="team-a", decided_on="2026-07-01"),
        _record("p2", "accepted", "2026-07-01T00:00:00Z", team="team-b", decided_on="2026-07-01"),
    ]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records), team="team-a")

    # Assert
    assert result.patch_count == 1
    assert result.team == "team-a"


def test_summarize_periodで絞り込んだ場合_該当月のみ集計されること(tmp_path):
    # Arrange
    records = [
        _accepted("p1", "01"),
        _record("p2", "accepted", "2026-08-01T00:00:00Z", decided_on="2026-08-01"),
    ]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records), period="2026-07")

    # Assert
    assert result.patch_count == 1
    assert result.period == "2026-07"


def test_summarize_一致するrecordがない場合_例外なく空の結果を返すこと(tmp_path):
    # Arrange
    records = [_accepted("p1", "01")]

    # Act
    result = sd.summarize(_write_jsonl(tmp_path, records), team="no-such-team")
    text = sd.render_text(result)

    # Assert
    assert result.patch_count == 0
    assert "No records matched" in text


# --- discard_reason validation ----------------------------------------------

def test_summarize_未宣言のdiscard_reasonの場合_InputErrorになること(tmp_path):
    # Arrange
    records = [_discarded("p1", "01", "not_a_declared_reason")]

    # Act & Assert
    with pytest.raises(sd.InputError, match="unknown discard_reason"):
        sd.summarize(_write_jsonl(tmp_path, records))


def test_summarize_overlayが追加したdiscard_reasonの場合_受理されること(tmp_path):
    # Arrange
    records = [_discarded("p1", "01", "vendor_contract_conflict")]

    # Act
    result = sd.summarize(
        _write_jsonl(tmp_path, records),
        overlay_paths=[patch_decision_team_bands_overlay_path()],
    )

    # Assert
    assert result.reason_counts == {"vendor_contract_conflict": 1}


# --- declared_reason_ids -----------------------------------------------------

def test_declared_reason_ids_base定義の場合_5件の理由idを返すこと():
    # Arrange
    defn = ov.load_yaml(patch_decision_path())

    # Act
    ids = sd.declared_reason_ids(defn)

    # Assert
    assert ids == {
        "never_cheap_rejected",
        "test_integrity_failed",
        "probe_oversized",
        "owner_unassignable",
        "cost_not_worth",
    }


# --- load_bands ---------------------------------------------------------------

def test_load_bands_baseの場合_空listを返すこと():
    # Arrange
    defn = ov.load_yaml(patch_decision_path())

    # Act
    bands = sd.load_bands(defn)

    # Assert
    assert bands == []


def test_load_bands_overlayでbandsを追加した場合_low昇順で返ること():
    # Arrange
    base = ov.load_yaml(patch_decision_path())
    merged = ov.apply_overlays(base, [patch_decision_team_bands_overlay_path()]).merged

    # Act
    bands = sd.load_bands(merged)

    # Assert
    assert [b.id for b in bands] == [
        "sunk_cost_suspected", "healthy", "overproduction_suspected",
    ]


@pytest.mark.parametrize(
    ("low", "high"),
    [
        pytest.param(0.5, 0.2, id="low_がhigh以上の場合_InputErrorになること"),
        pytest.param(0.2, 0.2, id="low_とhighが同値の場合_InputErrorになること"),
        pytest.param(-0.1, 0.5, id="low_が範囲外の場合_InputErrorになること"),
        pytest.param(0.2, 1.5, id="high_が範囲外の場合_InputErrorになること"),
    ],
)
def test_load_bands_不正な数値rangeの場合_InputErrorになること(low, high):
    # Arrange
    defn = {
        "version": 1,
        "name": "patch-decision",
        "separator": ".",
        "items": [
            {"id": "bands", "kind": "lookup"},
            {
                "id": "bands.bad", "kind": "lookup", "applies_to": "discard_rate",
                "low": low, "high": high, "label": "bad", "label_ja": "不正",
            },
        ],
    }

    # Act & Assert
    with pytest.raises(sd.InputError):
        sd.load_bands(defn)


def test_load_bands_必須field欠落の場合_InputErrorになること():
    # Arrange
    defn = {
        "version": 1,
        "name": "patch-decision",
        "separator": ".",
        "items": [
            {"id": "bands", "kind": "lookup"},
            {"id": "bands.bad", "kind": "lookup", "applies_to": "discard_rate", "low": 0.0},
        ],
    }

    # Act & Assert
    with pytest.raises(sd.InputError, match="missing required band fields"):
        sd.load_bands(defn)


def test_load_bands_applies_toが未知metricの場合_InputErrorになること():
    # Arrange
    defn = {
        "version": 1,
        "name": "patch-decision",
        "separator": ".",
        "items": [
            {"id": "bands", "kind": "lookup"},
            {
                "id": "bands.bad", "kind": "lookup", "applies_to": "acceptance_rate",
                "low": 0.0, "high": 0.5, "label": "bad", "label_ja": "不正",
            },
        ],
    }

    # Act & Assert
    with pytest.raises(sd.InputError, match="applies_to"):
        sd.load_bands(defn)


def test_load_bands_区間が重複した場合_InputErrorになること():
    # Arrange
    defn = {
        "version": 1,
        "name": "patch-decision",
        "separator": ".",
        "items": [
            {"id": "bands", "kind": "lookup"},
            {
                "id": "bands.a", "kind": "lookup", "applies_to": "discard_rate",
                "low": 0.0, "high": 0.5, "label": "a", "label_ja": "a",
            },
            {
                "id": "bands.b", "kind": "lookup", "applies_to": "discard_rate",
                "low": 0.4, "high": 0.9, "label": "b", "label_ja": "b",
            },
        ],
    }

    # Act & Assert
    with pytest.raises(sd.InputError, match="overlap"):
        sd.load_bands(defn)


def test_band_contains_境界値の場合_半開区間として判定すること():
    # Arrange
    band = sd.Band(id="x", low=0.1, high=0.2, label="x", label_ja="x")

    # Act
    low_included = band.contains(0.1)
    high_excluded = band.contains(0.2)

    # Assert
    assert low_included is True
    assert high_excluded is False


# --- overlay-injected invalid band must be rejected at summarize() too ------

def test_summarize_overlayが不正なbandsを注入した場合_InputErrorになること(tmp_path):
    # Arrange
    overlay = tmp_path / "bad-band.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-decision\nadd:\n"
        "  - id: bands.bad\n    kind: lookup\n    applies_to: discard_rate\n"
        "    low: 0.6\n    high: 0.2\n    label: bad\n    label_ja: 不正\n",
        encoding="utf-8",
    )
    records = [_accepted("p1", "01")]

    # Act & Assert
    with pytest.raises(sd.InputError, match="low must be strictly less than high"):
        sd.summarize(_write_jsonl(tmp_path, records), overlay_paths=[overlay])


# --- band matching in a summarized result -----------------------------------

def test_summarize_shipped_overlayを適用した場合_discard_rateに一致するbandが選ばれること(tmp_path):
    # Arrange
    records = [
        _accepted("p1", "01"),
        _accepted("p2", "02"),
        _accepted("p3", "03"),
        _discarded("p4", "04", "cost_not_worth"),
    ]  # discard_rate = 1/4 = 0.25 -> healthy band [0.15, 0.5)

    # Act
    result = sd.summarize(
        _write_jsonl(tmp_path, records),
        overlay_paths=[patch_decision_team_bands_overlay_path()],
    )

    # Assert
    assert result.matched_band is not None
    assert result.matched_band.id == "healthy"


# --- shipped sample numbers (pinned) ----------------------------------------

def test_summarize_ミドリ精機sampleの場合_期待する集計値になること():
    # Act
    result = sd.summarize(sample_patch_decisions_midori_path())

    # Assert
    assert result.record_count == 14
    assert result.patch_count == 13
    assert result.pending == 1
    assert result.discarded == 3
    assert result.decided == 12
    assert result.discard_rate == pytest.approx(0.25)
    assert result.decided_rate == pytest.approx(12 / 13)
    assert len(result.red_accepted) == 1
    assert len(result.yellow_accepted) == 2
    assert result.exit_code == 2


def test_summarize_demo_from_fixturesの場合_期待する集計値になること():
    # Act
    result = sd.summarize(sample_patch_decisions_demo_path())

    # Assert
    assert result.record_count == 5
    assert result.patch_count == 5
    assert result.discarded == 0
    assert result.decided == 5
    assert result.discard_rate == pytest.approx(0.0)
    assert len(result.red_accepted) == 2
    assert result.exit_code == 2


# --- render_json shape -------------------------------------------------------

def test_render_json_サンプルを集計した場合_discard_reasonsのshareが合計100パーセントであること():
    # Act
    result = sd.summarize(sample_patch_decisions_midori_path())
    payload = json.loads(sd.render_json(result))

    # Assert
    total_share = sum(r["share_of_discards"] for r in payload["discard_reasons"])
    assert total_share == pytest.approx(1.0)
    assert payload["discard_rate"] == pytest.approx(0.25)
    assert payload["exit_code"] == 2


# --- schema の条件必須/条件禁止 ------------------------------------------------

def test_summarize_pendingにdecided_onを付けた場合_schema違反で拒否されること(tmp_path):
    """pending は「まだ決めていない」状態なので、決定日を持てば記録が自己矛盾する。"""
    # Arrange
    record = _record("p1", "pending", "2026-07-01T09:00:00Z", decided_on="2026-07-01")
    path = _write_jsonl(tmp_path, [record])

    # Act & Assert
    with pytest.raises(sd.InputError, match="schema violation"):
        sd.summarize(path)


def test_summarize_決定済みにdecided_onが無い場合_schema違反で拒否されること(tmp_path):
    """決定済みに日付が無いと期間バケットに載らず、月次集計から静かに漏れる。"""
    # Arrange
    record = _record("p1", "accepted", "2026-07-01T09:00:00Z")
    path = _write_jsonl(tmp_path, [record])

    # Act & Assert
    with pytest.raises(sd.InputError, match="schema violation"):
        sd.summarize(path)


def test_summarize_acceptedにdiscard_reasonを付けた場合_schema違反で拒否されること(tmp_path):
    """採用に破棄理由が付くと、理由内訳の分母 (破棄件数) と件数が食い違う。"""
    # Arrange
    record = _record(
        "p1",
        "accepted",
        "2026-07-01T09:00:00Z",
        decided_on="2026-07-01",
        discard_reason="cost_not_worth",
    )
    path = _write_jsonl(tmp_path, [record])

    # Act & Assert
    with pytest.raises(sd.InputError, match="schema violation"):
        sd.summarize(path)


def test_summarize_discardedにdiscard_reasonが無い場合_schema違反で拒否されること(tmp_path):
    """理由なしの破棄を許すと、率は出ても打つ手が決まらない。"""
    # Arrange
    record = _record("p1", "discarded", "2026-07-01T09:00:00Z", decided_on="2026-07-01")
    path = _write_jsonl(tmp_path, [record])

    # Act & Assert
    with pytest.raises(sd.InputError, match="schema violation"):
        sd.summarize(path)
