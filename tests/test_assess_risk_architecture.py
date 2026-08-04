"""Unit tests for the risk-architecture adequacy check (assess_risk_architecture)."""
from __future__ import annotations

import yaml
import pytest

import overlay_scoring as ov
from adr import assess_risk_architecture as ra
from conftest import risk_architecture_path, sample_risk_architecture_path


def _definition() -> dict:
    return ov.load_yaml(risk_architecture_path())


def _full_answers(**overrides) -> dict:
    """全問回答のベースライン: 弱=yes / 強=no (全能力 1 点), owners 全て yes.

    profile も全次元 1 (total 7 = hybrid 帯) になるので、シナリオ採点と
    owners ゲートが適用される状態から個別ケースを上書きして作る。
    """
    answers: dict[str, str] = {}
    for gid, group in ov.group_items(_definition()).items():
        for leaf in group["leaves"]:
            if gid == "owners":
                answers[leaf["id"]] = "yes"
            else:
                answers[leaf["id"]] = "yes" if leaf["strength"] == "weak" else "no"
    answers.update(overrides)
    return answers


def _write_input(tmp_path, answers: dict, organization: str = "テスト組織"):
    p = tmp_path / "org.yaml"
    p.write_text(
        yaml.safe_dump({"organization": organization, "answers": answers}, allow_unicode=True),
        encoding="utf-8",
    )
    return p


def _scenario(result: ra.AssessResult, sid: str) -> ra.ScenarioResult:
    return next(s for s in result.scenarios if s.id == sid)


# --- 単調 2 問の写像 ---------------------------------------------------------

@pytest.mark.parametrize(
    ("weak", "strong", "expected"),
    [("no", "no", 0), ("yes", "no", 1), ("yes", "yes", 2)],
    ids=[
        "両方noの場合_0点であること",
        "弱のみyesの場合_1点であること",
        "両方yesの場合_2点であること",
    ],
)
def test_assess_単調2問の回答組を渡した場合_論文の3値尺度に写像されること(tmp_path, weak, strong, expected):
    """no/no=0, yes/no=1, yes/yes=2 が論文の {0,1,2} 順序尺度を保存する。"""
    # Arrange
    answers = _full_answers(**{"scenario_a.D1": weak, "scenario_a.D2": strong})
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    assert _scenario(result, "scenario_a").capabilities["detection"].score == expected


def test_assess_強がyesで弱がnoの場合_矛盾としてInputErrorになること(tmp_path):
    """強い能力は弱い能力を含意する: no/yes を warning で採点continueしない (fail-closed)。"""
    # Arrange
    answers = _full_answers(**{"scenario_a.D1": "no", "scenario_a.D2": "yes"})
    # Act & Assert
    with pytest.raises(ra.InputError, match="contradicts"):
        ra.assess(_write_input(tmp_path, answers))


# --- band 境界 ---------------------------------------------------------------

@pytest.mark.parametrize(
    ("d", "c", "s", "band"),
    [(1, 1, 0, "Low"), (1, 1, 1, "Medium"), (2, 1, 1, "Medium"), (2, 2, 1, "High")],
    ids=[
        "tau2の場合_Lowであること",
        "tau3の場合_Mediumであること",
        "tau4の場合_Mediumであること",
        "tau5の場合_Highであること",
    ],
)
def test_assess_tauがband境界の場合_論文のband区分になること(tmp_path, d, c, s, band):
    # Arrange
    def pair(cap_prefix: str, score: int) -> dict:
        return {
            f"scenario_a.{cap_prefix}1": "yes" if score >= 1 else "no",
            f"scenario_a.{cap_prefix}2": "yes" if score >= 2 else "no",
        }

    answers = _full_answers(**pair("D", d), **pair("C", c), **pair("S", s))
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    scenario = _scenario(result, "scenario_a")
    assert (scenario.tau, scenario.raw_band) == (d + c + s, band)


# --- サンプル診断 (論文 F3 採点例の再現) -------------------------------------

def test_assess_同梱サンプルを渡した場合_論文F3採点例のtau1がLowで再現されること():
    """論文の F3 (silent boundary contract drift, AI-native) 採点例
    d=0 / c=1 / s=0 -> tau=1 Low を参照基準としてサンプルに固定する。"""
    # Act
    result = ra.assess(sample_risk_architecture_path())
    # Assert
    drift = _scenario(result, "scenario_f_drift")
    caps = {c.capability: c.score for c in drift.capabilities.values()}
    assert caps == {"detection": 0, "containment": 1, "escalation": 0}
    assert (drift.tau, drift.raw_band) == (1, "Low")


def test_assess_同梱サンプルを渡した場合_owner不在でBLOCKとexit2になること():
    # Act
    result = ra.assess(sample_risk_architecture_path())
    # Assert
    assert result.profile.band == "ai_native"
    assert result.owners.missing == ["boundary_channel_owner"]
    assert result.conclusion == "BLOCK"
    assert ra.exit_code_for(result) == 2


# --- owners ゲート (raw と effective の分離) ---------------------------------

def test_assess_owner不在でrawがMediumの場合_effectiveだけがLowにcapされること(tmp_path):
    """owner ゲートは raw band を書き換えない (製品独自ゲートであることを
    出力で追跡できるよう、raw / effective / capped_by を分離して残す)。"""
    # Arrange: f_rollback を tau3 Medium にし、boundary owner だけ不在にする
    answers = _full_answers(**{"owners.O3": "no"})
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    rollback = _scenario(result, "scenario_f_rollback")
    assert rollback.raw_band == "Medium"
    assert rollback.effective_band == "Low"
    assert rollback.gated_by_owner == "boundary_channel_owner"
    assert result.conclusion == "BLOCK"


def test_assess_gated_byを持たないシナリオの場合_owner不在でもcapされないこと(tmp_path):
    # Arrange: scenario_a は owner ゲート対象外
    answers = _full_answers(**{"owners.O3": "no"})
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    scenario_a = _scenario(result, "scenario_a")
    assert scenario_a.raw_band == scenario_a.effective_band == "Medium"
    assert scenario_a.gated_by_owner is None


# --- profile 帯と適用契約 ----------------------------------------------------

def test_assess_全次元がpure_seの場合_conclusionがNOT_APPLICABLEでexit0になること(tmp_path):
    """pure-SE 帯にはシナリオ採点を強制しない: 論文はシナリオごとに前提の
    複雑度を持ち、全プロファイルへ強制すると結果が反転する。"""
    # Arrange
    answers = _full_answers()
    for qid in list(answers):
        if qid.startswith("profile."):
            answers[qid] = "no"
    answers["owners.O3"] = "no"  # owner 不在でもゲートは適用されない
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    assert result.profile.band == "pure_se"
    assert result.applicable is False
    assert result.conclusion == "NOT_APPLICABLE"
    assert ra.exit_code_for(result) == 0
    rollback = _scenario(result, "scenario_f_rollback")
    assert rollback.effective_band == rollback.raw_band  # cap されない


def test_assess_合計はpure_se帯でもD2が自律実行の場合_ゲートが適用されBLOCKになること(tmp_path):
    """D2 (行動自律性) は論文が最強のプロファイル遷移シグナルとする次元:
    合計帯の低さで多段自律実行チームを NOT_APPLICABLE に逃がすと偽陰性になる。"""
    # Arrange: D2 だけ 2、他次元 0 (total 2 = pure_se 帯)、全シナリオ 0 点 + owner 全不在
    answers = _full_answers()
    for qid in list(answers):
        if qid.startswith("profile."):
            answers[qid] = "no"
        elif qid.startswith("scenario_"):
            answers[qid] = "no"
    answers["profile.D2_HYBRID"] = "yes"
    answers["profile.D2_NATIVE"] = "yes"
    answers["owners.O1"] = answers["owners.O2"] = answers["owners.O3"] = "no"
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    assert result.profile.band == "pure_se"
    assert result.applicable is True
    assert result.conclusion == "BLOCK"
    assert ra.exit_code_for(result) == 2


def test_assess_pure_se帯でD2が人間承認どまりの場合_NOT_APPLICABLEのままであること(tmp_path):
    """D2=1 (AI が提案し人間が不可逆操作を承認) は多段自律実行ではない:
    D2=1 までゲートを広げると hybrid 未満の組織を誤って BLOCK する (偽陽性)。"""
    # Arrange: D2 だけ 1、他次元 0 (total 1 = pure_se 帯)、owner 全不在
    answers = _full_answers()
    for qid in list(answers):
        if qid.startswith("profile."):
            answers[qid] = "no"
    answers["profile.D2_HYBRID"] = "yes"
    answers["owners.O1"] = answers["owners.O2"] = answers["owners.O3"] = "no"
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    assert result.profile.band == "pure_se"
    assert result.applicable is False
    assert result.conclusion == "NOT_APPLICABLE"
    assert ra.exit_code_for(result) == 0


def test_assess_case_evidenceを集約した場合_derived_counterfactual注記が含まれること():
    """skill は JSON の case_evidence を確度ラベルごと引用する契約なので、
    楽観バイアス注記 (claim_needs_verification) が結果に載っていることを固定する。"""
    # Act
    result = ra.assess(sample_risk_architecture_path())
    # Assert
    labels = {e.get("confidence") for e in result.case_evidence}
    assert "claim_needs_verification" in labels
    assert any("counterfactual" in e.get("text", "").lower() for e in result.case_evidence)


def test_assess_重複keyを含むoverlayを渡した場合_InputErrorになること(tmp_path):
    """check-overlay は重複 YAML key を拒否する: 実行側が last-key-wins で
    受理すると、事前検査と実運用の契約が食い違う。"""
    # Arrange
    overlay_path = tmp_path / "dup.yaml"
    overlay_path.write_text(
        "version: 1\nextends: risk-architecture\n"
        "strengthen:\n  scenario_a:\n    high_min: 6\n    high_min: 5\n",
        encoding="utf-8",
    )
    answers = _full_answers()
    # Act & Assert
    with pytest.raises(ra.InputError, match="duplicate key"):
        ra.assess(_write_input(tmp_path, answers), overlay_paths=[overlay_path])


def test_assess_profileの7値ベクトルを渡した場合_次元ごとの値が出力に保持されること(tmp_path):
    # Arrange: d1 だけ 2、残り 1 -> total 8 (hybrid)
    answers = _full_answers(**{"profile.D1_NATIVE": "yes"})
    # Act
    result = ra.assess(_write_input(tmp_path, answers))
    # Assert
    assert result.profile.dimensions == {"d1": 2, "d2": 1, "d3": 1, "d4": 1, "d5": 1, "d6": 1, "d7": 1}
    assert result.profile.total == 8
    assert result.profile.band == "hybrid"


# --- fail-closed 契約 --------------------------------------------------------

def test_assess_回答が欠けている場合_欠落idを列挙したInputErrorになること(tmp_path):
    # Arrange
    answers = _full_answers()
    del answers["scenario_b.C1"]
    # Act & Assert
    with pytest.raises(ra.InputError, match="missing answers for: .*scenario_b.C1"):
        ra.assess(_write_input(tmp_path, answers))


def test_assess_曖昧な回答値の場合_InputErrorになること(tmp_path):
    # Arrange
    answers = _full_answers(**{"scenario_b.C1": "maybe"})
    # Act & Assert
    with pytest.raises(ra.InputError, match="invalid answers"):
        ra.assess(_write_input(tmp_path, answers))


# --- overlay と契約 validator ------------------------------------------------

def _scenario_x_overlay_items() -> list[dict]:
    items = [{"id": "scenario_x", "name": "custom", "name_ja": "自社シナリオ",
              "cluster": "X", "medium_min": 3, "high_min": 5}]
    for cap, prefix in (("detection", "D"), ("containment", "C"), ("escalation", "S")):
        for strength, n in (("weak", "1"), ("strong", "2")):
            items.append({
                "id": f"scenario_x.{prefix}{n}", "capability": cap, "strength": strength,
                "text": f"{cap} {strength}", "text_ja": f"{cap} {strength} の質問",
            })
    return items


def test_assess_新シナリオgroup一式のoverlayを適用した場合_追加シナリオも採点されること(tmp_path):
    # Arrange
    overlay = {"version": 1, "extends": "risk-architecture", "add": _scenario_x_overlay_items()}
    overlay_path = tmp_path / "extra-scenario.yaml"
    overlay_path.write_text(yaml.safe_dump(overlay, allow_unicode=True), encoding="utf-8")
    answers = _full_answers()
    for n in ("D1", "D2", "C1", "C2", "S1", "S2"):
        answers[f"scenario_x.{n}"] = "yes"
    # Act
    result = ra.assess(_write_input(tmp_path, answers), overlay_paths=[overlay_path])
    # Assert
    scenario_x = _scenario(result, "scenario_x")
    assert (scenario_x.tau, scenario_x.raw_band) == (6, "High")


def test_validate_contract_既存シナリオに7問目を足した定義の場合_契約違反になること():
    """generic engine は scenario_* への leaf add を通すが、単調 2 問 x 3 能力の
    形状が壊れると {0,1,2} 尺度が壊れるため、契約 validator が拒否する。"""
    # Arrange
    overlay = {"extends": "risk-architecture",
               "add": [{"id": "scenario_a.D3", "capability": "detection",
                        "strength": "strong", "text": "x", "text_ja": "x"}]}
    merged = ov.apply_overlay(_definition(), overlay)
    assert merged.ok  # エンジンは通す
    # Act
    problems = ra.validate_contract(merged.merged)
    # Assert
    assert any("scenario_a" in p and "strength=strong" in p for p in problems)


def test_validate_contract_text_jaを欠いた追加シナリオの場合_契約違反になること():
    """リポ規約 (全質問に text / text_ja 併記) を overlay 追加分にも強制する。"""
    # Arrange
    items = _scenario_x_overlay_items()
    for item in items[1:]:
        del item["text_ja"]
    overlay = {"extends": "risk-architecture", "add": items}
    merged = ov.apply_overlay(_definition(), overlay)
    assert merged.ok  # エンジンは通す
    # Act
    problems = ra.validate_contract(merged.merged)
    # Assert
    assert any("non-empty text_ja" in p for p in problems)


def test_validate_contract_band範囲が逆転した定義の場合_契約違反になること():
    # Arrange
    defn = _definition()
    header = next(i for i in defn["items"] if i["id"] == "scenario_a")
    header["medium_min"], header["high_min"] = 5, 3
    # Act
    problems = ra.validate_contract(defn)
    # Assert
    assert any("medium_min <= high_min" in p for p in problems)


def test_validate_contract_gated_byが未知のowner参照の場合_契約違反になること():
    # Arrange
    defn = _definition()
    header = next(i for i in defn["items"] if i["id"] == "scenario_c")
    header["gated_by"] = "owners.NOPE"
    # Act
    problems = ra.validate_contract(defn)
    # Assert
    assert any("gated_by" in p for p in problems)


def test_validate_contract_同梱定義の場合_契約違反がないこと():
    # Act & Assert
    assert ra.validate_contract(_definition()) == []
