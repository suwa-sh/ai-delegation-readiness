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
)
def test_all_eight_axis_combinations(tmp_path, exposure, necessity, elasticity, expected):
    r = _screen_one(tmp_path, _answers(exposure, necessity, elasticity))
    assert r.type == expected


def test_sample_task_groups_expected_types_and_priority_order():
    result = st.screen(sample_task_groups_path())
    by_id = {g.id: g.type for g in result.task_groups}
    assert by_id == {
        "accounting_entry_check": "high_automation",
        "clinical_documentation": "reorganization",
        "financial_advisory_reports": "growth",
        "equipment_field_maintenance": "minimal_change",
    }
    # Output is sorted by delegation-design priority (reorganization first).
    assert [g.id for g in result.task_groups] == [
        "clinical_documentation",
        "accounting_entry_check",
        "financial_advisory_reports",
        "equipment_field_maintenance",
    ]
    assert result.exit_code == 0


# --- human_necessity threshold=1 (any single reason keeps humans) ------------

def test_single_necessity_yes_flips_axis_high(tmp_path):
    answers = _answers(True, False, False)
    answers["human_necessity.H3"] = True  # physical only
    r = _screen_one(tmp_path, answers)
    assert r.axes["human_necessity"].level == "high"
    assert r.type == "reorganization"
    # H3 is not a human_control question: no HITL flag.
    assert r.human_control_required is False


# --- HITL flag is independent of the type ------------------------------------

def test_growth_path_keeps_hitl_flag(tmp_path):
    """H1=yes must surface even when elasticity routes the group to growth."""
    answers = _answers(True, False, True)
    answers["human_necessity.H1"] = True
    r = _screen_one(tmp_path, answers)
    assert r.type == "growth"
    assert r.human_control_required is True
    assert r.human_control_yes_ids == ["human_necessity.H1"]
    assert "[HITL]" in st.render_text(st.ScreenResult(task_groups=[r]))


def test_no_hitl_flag_when_h1_no(tmp_path):
    r = _screen_one(tmp_path, _answers(True, False, False))
    assert r.human_control_required is False
    assert "[HITL]" not in st.render_text(st.ScreenResult(task_groups=[r]))


# --- fail-closed input contract ----------------------------------------------

def test_missing_answer_is_input_error_listing_ids(tmp_path):
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
    with pytest.raises(st.InputError) as e:
        st.screen(p)
    msg = str(e.value)
    assert "partial" in msg
    for qid in ("human_necessity.H1", "human_necessity.H2", "human_necessity.H3"):
        assert qid in msg


def test_non_mapping_input_is_input_error(tmp_path):
    p = _write(tmp_path, "- just\n- a list\n")
    with pytest.raises(st.InputError):
        st.screen(p)


def test_task_groups_not_a_list_is_input_error(tmp_path):
    p = _write(tmp_path, "task_groups: {oops: 1}\n")
    with pytest.raises(st.InputError):
        st.screen(p)


# --- overlay behaviour --------------------------------------------------------

def test_overlay_added_question_is_required_and_scored(tmp_path):
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
    with pytest.raises(st.InputError) as e:
        st.screen(p, overlay_paths=[overlay])
    assert "technical_exposure.E4" in str(e.value)

    # With the answer supplied, the added question participates in the score.
    p2 = _write_task_groups(
        tmp_path, {**base_answers, "technical_exposure.E4": True}, name="tg2.yaml"
    )
    result = st.screen(p2, overlay_paths=[overlay])
    assert result.task_groups[0].axes["technical_exposure"].score == 4


def test_render_json_includes_case_evidence():
    result = st.screen(sample_task_groups_path())
    payload = st.render_json(result)
    assert "case_evidence" in payload
    # The EU/US figure mix-up warning must travel with client-facing output.
    assert "misattributed" in payload
