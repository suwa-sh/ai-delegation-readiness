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

def test_sample_green_is_green_exit_0():
    r = tc.score(sample_task_contract_green_path())
    assert r.region == "green"
    assert r.exit_code == 0
    assert all(e.level == "present" for e in r.elements)


def test_sample_red_ai_judge_is_red_exit_2():
    r = tc.score(sample_task_contract_red_path())
    assert r.region == "red"
    assert r.exit_code == 2
    assert "ai_judge_without_iruler" in r.active_conditions


# --- presence levels --------------------------------------------------------

def test_all_present_human_is_green(tmp_path):
    c = _write(tmp_path, _ALL_PRESENT.format(stype="human", iruler="no"))
    r = tc.score(c)
    assert r.region == "green"
    assert r.exit_code == 0


def test_partial_element_is_yellow(tmp_path):
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
    r = tc.score(c)
    assert r.region == "yellow"
    assert r.exit_code == 1
    intent = next(e for e in r.elements if e.id == "intent")
    assert intent.level == "partial"


def test_absent_element_is_red(tmp_path):
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
    r = tc.score(c)
    assert r.region == "red"
    assert r.exit_code == 2
    assert "any_element_absent" in r.active_conditions


# --- iRULER safety gate -----------------------------------------------------

def test_ai_judge_without_iruler_is_red(tmp_path):
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler="no"))
    r = tc.score(c)
    assert r.region == "red"
    assert r.exit_code == 2


def test_ai_judge_with_iruler_is_green(tmp_path):
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler="yes"))
    r = tc.score(c)
    assert r.region == "green"


def test_two_stage_without_iruler_is_not_gated(tmp_path):
    # two_stage carries a human second stage, so the iRULER gate does not fire.
    c = _write(tmp_path, _ALL_PRESENT.format(stype="two_stage", iruler="no"))
    r = tc.score(c)
    assert r.region == "green"
    assert "ai_judge_without_iruler" not in r.active_conditions


@pytest.mark.parametrize("bad_iruler", ["2", "-1", "maybe", "0"])
def test_ai_judge_nonyes_iruler_fails_closed(tmp_path, bad_iruler):
    # The safety gate must not open on a stray truthy value (bool(2) is True).
    # Only an explicit yes counts as "in place".
    c = _write(tmp_path, _ALL_PRESENT.format(stype="ai_judge", iruler=bad_iruler))
    r = tc.score(c)
    assert r.region == "red", f"iruler={bad_iruler!r} should fail closed"


def test_ai_judge_missing_iruler_defaults_to_gated(tmp_path):
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
    r = tc.score(c)
    assert r.region == "red"


# --- scorer.type enum validation -------------------------------------------

def test_missing_scorer_type_raises_input_error(tmp_path):
    c = _write(
        tmp_path,
        """
        task: t
        answers:
          intent.I1: yes
          scorer.S1: yes
        """,
    )
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_invalid_scorer_type_raises_input_error(tmp_path):
    c = _write(tmp_path, _ALL_PRESENT.format(stype="robot", iruler="no"))
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_non_mapping_answers_raises_input_error(tmp_path):
    c = _write(tmp_path, "task: t\nanswers: just-a-string\n")
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_non_mapping_contract_raises_input_error(tmp_path):
    c = _write(tmp_path, "- a\n- b\n")  # a list, not a mapping
    with pytest.raises(tc.InputError):
        tc.score(c)


def test_zero_question_element_is_absent():
    # A required element group with no questions must score absent, not present.
    empty = tc._score_element("intent", {"header": {"threshold": 2}, "leaves": []}, {})
    assert empty.level == "absent"


# --- definition integrity + conformance ------------------------------------

def test_base_definition_validates():
    assert ov.validate_definition(ov.load_yaml(task_contract_path())) == []


def test_gate_policy_conforms_to_consumer_conditions():
    """Every non-'otherwise' token declared in the definition's gates.*.when
    must be an implemented condition, and every implemented condition must be
    referenced by the definition. This keeps the machine-readable gate policy
    and the consumer in lockstep (the definition alone reproduces the verdict).
    """
    defn = ov.load_yaml(task_contract_path())
    groups = ov.group_items(defn)
    gate_leaves = groups["gates"]["leaves"]

    declared_tokens: set[str] = set()
    for leaf in gate_leaves:
        when = leaf.get("when", [])
        if isinstance(when, str):
            when = [when]
        declared_tokens.update(when)
        assert "exit_code" in leaf, f"{leaf['id']} missing exit_code"

    known = set(tc.CONDITION_EVALUATORS) | {tc._OTHERWISE}
    assert declared_tokens <= known, f"unknown gate tokens: {declared_tokens - known}"
    # every implemented condition is actually used by the policy
    assert set(tc.CONDITION_EVALUATORS) <= declared_tokens

    # gates must end with an 'otherwise' fallback so a region always resolves
    last_when = gate_leaves[-1].get("when")
    assert last_when == [tc._OTHERWISE] or last_when == tc._OTHERWISE


def test_overlay_added_question_without_kind_is_scored():
    # An overlay adds questions to an element group and may omit ``kind``.
    # Those must still be scored (default question), while explicit data leaves
    # are excluded — otherwise overlay questions are silently dropped.
    group = {
        "header": {"threshold": 2},
        "leaves": [
            {"id": "intent.I1", "kind": "question"},
            {"id": "intent.I4", "text": "added by overlay, no kind"},
            {"id": "intent.type", "kind": "data"},
        ],
    }
    ids = {q["id"] for q in tc._question_leaves(group)}
    assert ids == {"intent.I1", "intent.I4"}


def test_exit_codes_match_regions():
    """Green/yellow/red leaves carry exit codes 0/1/2 respectively."""
    defn = ov.load_yaml(task_contract_path())
    by_slug = {
        leaf["id"].split(".", 1)[1]: int(leaf["exit_code"])
        for leaf in ov.group_items(defn)["gates"]["leaves"]
    }
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


def test_authz_overlay_strengthened_boundary_downgrades_a_base_green(tmp_path):
    """A contract that is GREEN on the base definition drops to YELLOW.

    All three base boundary questions are yes, so boundary is present under the
    base threshold of 2. Under the overlay the group needs 5 of 5 and neither
    added question is answered, so it drops to partial — the strengthened
    threshold actually bites instead of riding along.
    """
    path = _write(tmp_path, _ALL_PRESENT.format(stype="two_stage", iruler="no"))

    base = tc.score(path)
    assert base.region == "green"
    assert _element(base, "boundary").level == "present"

    overlaid = tc.score(path, overlay_paths=[_authz_contract_overlay_path()])
    assert _element(overlaid, "boundary").level == "partial"
    assert overlaid.region == "yellow"
    assert overlaid.exit_code == 1


def test_sample_authz_contract_is_yellow_on_the_added_question():
    """The bundled sample: everything declared except a bounded authority scope."""
    from conftest import sample_authz_contract_path
    result = tc.score(sample_authz_contract_path(),
                      overlay_paths=[_authz_contract_overlay_path()])
    boundary = _element(result, "boundary")
    assert boundary.level == "partial"
    assert boundary.no_ids == ["boundary.AZ2"]
    assert result.region == "yellow"
