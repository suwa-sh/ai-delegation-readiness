"""Transition screening tests (3 axes -> 4 AI-transition types)."""
from __future__ import annotations

import textwrap

import pytest
import yaml

from adr import screen_transition as st
from conftest import sample_task_groups_path


def _write(tmp_path, text, name="tg.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


def _write_task_groups(tmp_path, answers: dict, name="tg.yaml"):
    p = tmp_path / name
    p.write_text(
        yaml.safe_dump(
            {"task_groups": [{"id": "probe", "description": "probe", "answers": answers}]}
        )
    )
    return p


def _answers(exposure: bool, necessity: bool, elasticity: bool) -> dict:
    """Full answer set (fail-closed contract) for one axis-level triple."""
    return {
        "technical_exposure.E1": exposure,
        "technical_exposure.E2": exposure,
        "technical_exposure.E3": exposure,
        "human_necessity.H1": necessity,
        "human_necessity.H2": necessity,
        "human_necessity.H3": necessity,
        "demand_elasticity.D1": elasticity,
        "demand_elasticity.D2": elasticity,
        "demand_elasticity.D3": elasticity,
    }


def _screen_one(tmp_path, answers: dict) -> st.TaskGroupResult:
    p = _write_task_groups(tmp_path, answers)
    result = st.screen(p)
    assert len(result.task_groups) == 1
    return result.task_groups[0]


# --- full 8-combination conformance (decision-tree mapping) ------------------
# exposure low => minimal_change regardless of the other axes;
# exposure high & elastic => growth regardless of necessity;
# exposure high & inelastic => necessity splits reorganization / high_automation.

@pytest.mark.parametrize(
    "exposure,necessity,elasticity,expected",
    [
        (False, False, False, "minimal_change"),
        (False, False, True, "minimal_change"),
        (False, True, False, "minimal_change"),
        (False, True, True, "minimal_change"),
        (True, False, False, "high_automation"),
        (True, False, True, "growth"),
        (True, True, False, "reorganization"),
        (True, True, True, "growth"),
    ],
    ids=[
        "露出低_必要性低_弾力性低の場合_minimal_changeになること",
        "露出低_必要性低_弾力性高の場合_minimal_changeになること",
        "露出低_必要性高_弾力性低の場合_minimal_changeになること",
        "露出低_必要性高_弾力性高の場合_minimal_changeになること",
        "露出高_必要性低_弾力性低の場合_high_automationになること",
        "露出高_必要性低_弾力性高の場合_growthになること",
        "露出高_必要性高_弾力性低の場合_reorganizationになること",
        "露出高_必要性高_弾力性高の場合_growthになること",
    ],
)
def test_screen_3軸8通りの組み合わせの場合_決定木どおりの種別になること(
    tmp_path, exposure, necessity, elasticity, expected
):
    # Act
    r = _screen_one(tmp_path, _answers(exposure, necessity, elasticity))
    # Assert
    assert r.type == expected


def test_screen_サンプルタスク群を判定した場合_4種別が優先順位順に並ぶこと():
    # Act
    result = st.screen(sample_task_groups_path())
    by_id = {g.id: g.type for g in result.task_groups}
    # Assert
    assert by_id == {
        "financial_disclosure_draft": "reorganization",
        "expense_entry_check": "high_automation",
        "sales_proposal_draft": "growth",
        "equipment_maintenance": "minimal_change",
    }
    # Output is sorted by delegation-design priority (reorganization first).
    assert [g.id for g in result.task_groups] == [
        "financial_disclosure_draft",
        "expense_entry_check",
        "sales_proposal_draft",
        "equipment_maintenance",
    ]
    assert result.exit_code == 0


def test_screen_サンプルタスク群を判定した場合_H1のみがHITL対象になること():
    """HITL must come from H1 (regulated domains), not merely from a high
    human_necessity axis — disclosure carries H1=yes, the others must not."""
    # Act
    result = st.screen(sample_task_groups_path())
    hitl = {g.id: g.human_control_required for g in result.task_groups}
    # Assert
    assert hitl == {
        "financial_disclosure_draft": True,
        "expense_entry_check": False,
        "sales_proposal_draft": False,
        "equipment_maintenance": False,
    }
    disclosure = next(g for g in result.task_groups if g.id == "financial_disclosure_draft")
    assert disclosure.human_control_yes_ids == ["human_necessity.H1"]


# --- human_necessity threshold=1 (any single reason keeps humans) ------------

def test_screen_必要性理由が1つだけ真の場合_axisがhighになりreorganization判定されること(tmp_path):
    # Arrange
    answers = _answers(True, False, False)
    answers["human_necessity.H3"] = True  # physical only
    # Act
    r = _screen_one(tmp_path, answers)
    # Assert
    assert r.axes["human_necessity"].level == "high"
    assert r.type == "reorganization"
    # H3 is not a human_control question: no HITL flag.
    assert r.human_control_required is False


# --- HITL flag is independent of the type ------------------------------------

def test_screen_弾力性でgrowthに振り分けられた場合_H1由来のHITLフラグが立つこと(tmp_path):
    # Arrange
    answers = _answers(True, False, True)
    answers["human_necessity.H1"] = True
    # Act
    r = _screen_one(tmp_path, answers)
    # Assert
    assert r.type == "growth"
    assert r.human_control_required is True
    assert r.human_control_yes_ids == ["human_necessity.H1"]
    assert "[HITL]" in st.render_text(st.ScreenResult(task_groups=[r]))


def test_screen_H1が否の場合_HITLフラグが立たないこと(tmp_path):
    # Act
    r = _screen_one(tmp_path, _answers(True, False, False))
    # Assert
    assert r.human_control_required is False
    assert "[HITL]" not in st.render_text(st.ScreenResult(task_groups=[r]))


# --- fail-closed input contract ----------------------------------------------

def test_screen_human_necessityの回答が欠落している場合_InputErrorに欠落IDが列挙されること(tmp_path):
    # Arrange
    p = _write(
        tmp_path,
        """
        task_groups:
          - id: partial
            description: missing human_necessity answers
            answers:
              technical_exposure.E1: yes
              technical_exposure.E2: yes
              technical_exposure.E3: yes
              demand_elasticity.D1: no
              demand_elasticity.D2: no
              demand_elasticity.D3: no
        """,
    )
    # Act
    with pytest.raises(st.InputError) as e:
        st.screen(p)
    # Assert
    msg = str(e.value)
    assert "partial" in msg
    for qid in ("human_necessity.H1", "human_necessity.H2", "human_necessity.H3"):
        assert qid in msg


def test_screen_回答値が不正な場合_InputErrorに不正値が列挙されること(tmp_path):
    """Typos and out-of-range numbers must not silently score as yes/no.

    'yess' on H1 would otherwise score as no -> human_necessity low ->
    high_automation without HITL: the exact fail-open the contract forbids.
    """
    # Arrange
    answers = _answers(True, False, False)
    answers["human_necessity.H1"] = "yess"
    answers["demand_elasticity.D1"] = 2
    p = _write_task_groups(tmp_path, answers)
    # Act
    with pytest.raises(st.InputError) as e:
        st.screen(p)
    # Assert
    msg = str(e.value)
    assert "invalid answers" in msg
    assert "human_necessity.H1" in msg and "yess" in msg
    assert "demand_elasticity.D1" in msg


def test_screen_入力全体がmappingでない場合_InputErrorになること(tmp_path):
    # Arrange
    p = _write(tmp_path, "- just\n- a list\n")
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(p)


def test_screen_task_groupsがlistでない場合_InputErrorになること(tmp_path):
    # Arrange
    p = _write(tmp_path, "task_groups: {oops: 1}\n")
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(p)


def test_screen_task_groupsがnullまたは欠落している場合_InputErrorになること(tmp_path):
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(_write(tmp_path, "task_groups:\n", name="null.yaml"))
    with pytest.raises(st.InputError):
        st.screen(_write(tmp_path, "other_key: 1\n", name="absent.yaml"))


def test_screen_task_groupsの要素がmappingでない場合_InputErrorになること(tmp_path):
    # Arrange
    p = _write(tmp_path, "task_groups:\n  - just_a_string\n")
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(p)


def test_screen_answersの型が不正な場合_InputErrorになること(tmp_path):
    # Arrange
    p = _write(tmp_path, "task_groups:\n  - id: bad\n    answers: true\n")
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(p)


def test_screen_YAMLが壊れている場合_InputErrorになること(tmp_path):
    # Arrange
    p = _write(tmp_path, "task_groups: [unclosed\n  - {\n")
    # Act & Assert
    with pytest.raises(st.InputError):
        st.screen(p)


# --- overlay behaviour --------------------------------------------------------

def test_screen_overlayで質問を追加した場合_必須項目としてスコアに反映されること(tmp_path):
    # Arrange
    overlay = _write(
        tmp_path,
        """
        version: 1
        extends: transition-screening
        add:
          - id: "technical_exposure.E4"
            text: extra exposure question
        """,
        name="ov.yaml",
    )
    # Missing the added question now violates the fail-closed contract.
    base_answers = _answers(True, False, False)
    p = _write_task_groups(tmp_path, base_answers)
    # Act
    with pytest.raises(st.InputError) as e:
        st.screen(p, overlay_paths=[overlay])
    # Assert
    assert "technical_exposure.E4" in str(e.value)

    # With the answer supplied, the added question participates in the score.
    p2 = _write_task_groups(
        tmp_path, {**base_answers, "technical_exposure.E4": True}, name="tg2.yaml"
    )
    result = st.screen(p2, overlay_paths=[overlay])
    assert result.task_groups[0].axes["technical_exposure"].score == 4


def test_screen_overlayでhuman_controlフラグ付き質問を追加した場合_HITL判定と表示に反映されること(tmp_path):
    """A company overlay can add its own human_control question; the flag
    and the rendered text must cover it generically (not only base H1)."""
    # Arrange
    overlay = _write(
        tmp_path,
        """
        version: 1
        extends: transition-screening
        add:
          - id: "human_necessity.H4"
            text: Does company policy require a named human release decision?
            flag: human_control
        """,
        name="ov-hc.yaml",
    )
    answers = _answers(True, False, True)  # growth path, H1..H3 = no
    answers["human_necessity.H4"] = True
    p = _write_task_groups(tmp_path, answers)
    # Act
    result = st.screen(p, overlay_paths=[overlay])
    r = result.task_groups[0]
    # Assert
    assert r.human_control_required is True
    assert r.human_control_yes_ids == ["human_necessity.H4"]
    text = st.render_text(st.ScreenResult(task_groups=[r]))
    assert "[HITL]" in text and "human_necessity.H4" in text


def test_render_json_サンプルを出力した場合_case_evidenceが含まれること():
    # Arrange
    result = st.screen(sample_task_groups_path())
    # Act
    payload = st.render_json(result)
    # Assert
    assert "case_evidence" in payload
    # The EU/US figure mix-up warning must travel with client-facing output.
    assert "misattributed" in payload
