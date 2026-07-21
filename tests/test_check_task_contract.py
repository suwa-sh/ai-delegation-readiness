"""Task-contract execution-rubric scoring tests.

Covers the four-element presence scoring (present/partial/absent), the iRULER
safety gate, scorer.type enum validation, exit codes, and a conformance test
that keeps the definition's gate policy and the consumer's condition
evaluators in sync.
"""
from __future__ import annotations

import textwrap

import pytest
import overlay_scoring as ov

from adr import check_task_contract as tc
from conftest import (
    sample_task_contract_green_path,
    sample_task_contract_red_path,
    task_contract_path,
)


def _write(tmp_path, text, name="contract.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


_ALL_PRESENT = """
    task: t
    answers:
      intent.I1: yes
      intent.I2: yes
      intent.I3: yes
      boundary.B1: yes
      boundary.B2: yes
      boundary.B3: yes
      evidence.E1: yes
      evidence.E2: yes
      evidence.E3: yes
      scorer.S1: yes
      scorer.S2: yes
      scorer.type: {stype}
      scorer.iruler_double_eval: {iruler}
"""


# --- samples ----------------------------------------------------------------

def test_score_サンプルのgreenパスの場合_regionがgreenでexit_code0になること():
    # Act
    r = tc.score(sample_task_contract_green_path())
    # Assert
    assert r.region == "green"
    assert r.exit_code == 0
    assert all(e.level == "present" for e in r.elements)


def test_score_サンプルのred_ai_judgeパスの場合_regionがredでexit_code2になること():
    # Act
    r = tc.score(sample_task_contract_red_path())
    # Assert
    assert r.region == "red"
    assert r.exit_code == 2
    assert "ai_judge_without_iruler" in r.active_conditions


# --- presence levels --------------------------------------------------------

def test_score_全要素presentでscorerがhumanの場合_greenになること(tmp_path):
    # Arrange
    c = _write(tmp_path, _ALL_PRESENT.format(stype="human", iruler="no"))
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "green"
    assert r.exit_code == 0


def test_score_intentの回答が一部のみの場合_partialとしてyellowになること(tmp_path):
    # Arrange
    # intent has only 1/3 yes -> partial; nothing absent; scorer human -> no gate
    c = _write(
        tmp_path,
        """
        task: t
        answers:
          intent.I1: yes
          boundary.B1: yes
          boundary.B2: yes
          evidence.E1: yes
          evidence.E2: yes
          scorer.S1: yes
          scorer.S2: yes
          scorer.type: human
        """,
    )
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "yellow"
    assert r.exit_code == 1
    intent = next(e for e in r.elements if e.id == "intent")
    assert intent.level == "partial"


def test_score_boundaryが全てnoの場合_absentとしてredになること(tmp_path):
    # Arrange
    # boundary entirely no -> absent -> red, even with a human scorer
    c = _write(
        tmp_path,
        """
        task: t
        answers:
          intent.I1: yes
          intent.I2: yes
          boundary.B1: no
          boundary.B2: no
          boundary.B3: no
          evidence.E1: yes
          evidence.E2: yes
          scorer.S1: yes
          scorer.S2: yes
          scorer.type: two_stage
        """,
    )
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "red"
    assert r.exit_code == 2
    assert "any_element_absent" in r.active_conditions


# --- iRULER safety gate -----------------------------------------------------

def test_score_ai_judgeでiRULER二重評価が無い場合_redで止まること(tmp_path):
    # Arrange
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler="no"))
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "red"
    assert r.exit_code == 2


def test_score_ai_judgeでiRULER二重評価がある場合_greenになること(tmp_path):
    # Arrange
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler="yes"))
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "green"


def test_score_two_stageでiRULERが無い場合_ゲートされずgreenになること(tmp_path):
    # Arrange
    # two_stage carries a human second stage, so the iRULER gate does not fire.
    c = _write(tmp_path, _ALL_PRESENT.format(stype="two_stage", iruler="no"))
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "green"
    assert "ai_judge_without_iruler" not in r.active_conditions


@pytest.mark.parametrize(
    "bad_iruler",
    ["2", "-1", "maybe", "0"],
    ids=[
        "iruler_2の場合_安全側に倒れてredになること",
        "iruler_-1の場合_安全側に倒れてredになること",
        "iruler_maybeの場合_安全側に倒れてredになること",
        "iruler_0の場合_安全側に倒れてredになること",
    ],
)
def test_score_ai_judgeでiruler_double_evalがyes以外の場合_安全側に倒れてredになること(tmp_path, bad_iruler):
    # Arrange
    # The safety gate must not open on a stray truthy value (bool(2) is True).
    # Only an explicit yes counts as "in place".
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler=bad_iruler))
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "red", f"iruler={bad_iruler!r} should fail closed"


def test_score_ai_judgeでiruler_double_evalが未設定の場合_ゲートされてredになること(tmp_path):
    # Arrange
    # iruler unset (unparseable) counts as "not in place" -> gate fires.
    c = _write(
        tmp_path,
        """
        task: t
        answers:
          intent.I1: yes
          intent.I2: yes
          boundary.B1: yes
          boundary.B2: yes
          evidence.E1: yes
          evidence.E2: yes
          scorer.S1: yes
          scorer.S2: yes
          scorer.type: ai_judge
        """,
    )
    # Act
    r = tc.score(c)
    # Assert
    assert r.region == "red"


# --- scorer.type enum validation -------------------------------------------

def test_score_scorer_typeが無い場合_InputErrorになること(tmp_path):
    # Arrange
    c = _write(
        tmp_path,
        """
        task: t
        answers:
          intent.I1: yes
          scorer.S1: yes
        """,
    )
    # Act & Assert
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_score_scorer_typeが不正な値の場合_InputErrorになること(tmp_path):
    # Arrange
    c = _write(tmp_path, _ALL_PRESENT.format(stype="robot", iruler="no"))
    # Act & Assert
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_score_answersがmapping以外の場合_InputErrorになること(tmp_path):
    # Arrange
    c = _write(tmp_path, "task: t\nanswers: just-a-string\n")
    # Act & Assert
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_score_contractがmapping以外の場合_InputErrorになること(tmp_path):
    # Arrange
    c = _write(tmp_path, "- a\n- b\n")  # a list, not a mapping
    # Act & Assert
    with pytest.raises(tc.InputError):
        tc.score(c)


def test__score_element_質問数が0の場合_absentになること():
    # A required element group with no questions must score absent, not present.
    # Act
    empty = tc._score_element("intent", {"header": {"threshold": 2}, "leaves": []}, {})
    # Assert
    assert empty.level == "absent"


# --- definition integrity + conformance ------------------------------------

def test_validate_definition_ベース定義の場合_エラーが無いこと():
    # Act & Assert
    assert ov.validate_definition(ov.load_yaml(task_contract_path())) == []


def test_group_items_gates_leavesのwhenトークンとCONDITION_EVALUATORSを比較した場合_過不足なく一致すること():
    """Keeps the machine-readable gate policy and the consumer in lockstep
    (the definition alone reproduces the verdict)."""
    # Arrange
    defn = ov.load_yaml(task_contract_path())
    groups = ov.group_items(defn)
    gate_leaves = groups["gates"]["leaves"]

    # Act
    declared_tokens: set[str] = set()
    for leaf in gate_leaves:
        when = leaf.get("when", [])
        if isinstance(when, str):
            when = [when]
        declared_tokens.update(when)
        assert "exit_code" in leaf, f"{leaf['id']} missing exit_code"

    # Assert
    known = set(tc.CONDITION_EVALUATORS) | {tc._OTHERWISE}
    assert declared_tokens <= known, f"unknown gate tokens: {declared_tokens - known}"
    # every implemented condition is actually used by the policy
    assert set(tc.CONDITION_EVALUATORS) <= declared_tokens

    # gates must end with an 'otherwise' fallback so a region always resolves
    last_when = gate_leaves[-1].get("when")
    assert last_when == [tc._OTHERWISE] or last_when == tc._OTHERWISE


def test__question_leaves_overlayでkindを省略した質問を追加した場合_その質問もスコア対象になること():
    # An overlay adds questions to an element group and may omit ``kind``.
    # Those must still be scored (default question), while explicit data leaves
    # are excluded — otherwise overlay questions are silently dropped.
    # Arrange
    group = {
        "header": {"threshold": 2},
        "leaves": [
            {"id": "intent.I1", "kind": "question"},
            {"id": "intent.I4", "text": "added by overlay, no kind"},
            {"id": "intent.type", "kind": "data"},
        ],
    }
    # Act
    ids = {q["id"] for q in tc._question_leaves(group)}
    # Assert
    assert ids == {"intent.I1", "intent.I4"}


def test_group_items_gates_leavesのgreen_yellow_redを見た場合_exit_codeが0_1_2に対応すること():
    # Arrange
    defn = ov.load_yaml(task_contract_path())
    # Act
    by_slug = {
        leaf["id"].split(".", 1)[1]: int(leaf["exit_code"])
        for leaf in ov.group_items(defn)["gates"]["leaves"]
    }
    # Assert
    assert by_slug == {"green": 0, "yellow": 1, "red": 2}


# --- agent-authorization overlay (examples/overlays/agent-authorization) -----
# boundary gains AZ1/AZ2 and its count threshold is strengthened 2 -> 5. These
# pin the monotonicity rule the definition only states in a comment: adding
# presence questions without raising the threshold would make the group
# relatively easier to pass.

def _authz_contract_overlay_path():
    from conftest import authz_overlay_task_contract_path
    return authz_overlay_task_contract_path()


def _element(result, element_id):
    return next(e for e in result.elements if e.id == element_id)


def test_score_authz_overlayで閾値を強化した場合_base_greenがyellowに落ちること(tmp_path):
    """All three base boundary questions are yes, so boundary is present under the
    base threshold of 2. Under the overlay the group needs 5 of 5 and neither
    added question is answered, so it drops to partial — the strengthened
    threshold actually bites instead of riding along.
    """
    # Arrange
    path = _write(tmp_path, _ALL_PRESENT.format(stype="two_stage", iruler="no"))

    # Act
    base = tc.score(path)
    assert base.region == "green"
    assert _element(base, "boundary").level == "present"

    overlaid = tc.score(path, overlay_paths=[_authz_contract_overlay_path()])
    # Assert
    assert _element(overlaid, "boundary").level == "partial"
    assert overlaid.region == "yellow"
    assert overlaid.exit_code == 1


def test_score_authzサンプルで追加質問が未回答の場合_boundaryがpartialでyellowになること():
    """The bundled sample: everything declared except a bounded authority scope."""
    # Arrange
    from conftest import sample_authz_contract_path

    # Act
    result = tc.score(sample_authz_contract_path(),
                      overlay_paths=[_authz_contract_overlay_path()])
    # Assert
    boundary = _element(result, "boundary")
    assert boundary.level == "partial"
    assert boundary.no_ids == ["boundary.AZ2"]
    assert result.region == "yellow"
