"""4-layer + efficacy readiness scoring tests."""
from __future__ import annotations

import textwrap

import pytest
import yaml

import overlay_scoring as ov
from adr import check_readiness as cr
from conftest import sample_business_path, four_layer_path, EXAMPLES_DIR


def ajinomoto_discovery_team_path():
    return EXAMPLES_DIR / "business" / "ajinomoto-discovery-team.csv"


def _write(tmp_path, text, name="biz.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


def _all_yes_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    return {item["id"]: "yes" for item in base["items"] if ov.is_leaf(item["id"], ov.separator_of(base))}


def test_all_yes_passes(tmp_path):
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "all-yes", "answers": _all_yes_answers()}))
    result = cr.check(biz_path)
    assert result.conclusion == "PASS"
    assert cr.exit_code_for(result) == 0
    assert result.blocked_from is None


def test_sample_business_returns_block():
    """The bundled sample business is intentionally L4-incomplete."""
    result = cr.check(sample_business_path())
    assert result.conclusion == "BLOCK"
    assert cr.exit_code_for(result) == 2
    assert result.blocked_from == "L1"  # L1 is the first non-PASS layer


def test_all_no_blocks(tmp_path):
    biz = _write(
        tmp_path,
        """
        target: all-no
        answers: {}
        """,
    )
    result = cr.check(biz)
    assert result.conclusion == "BLOCK"


def test_unknown_answer_is_treated_as_unknown(tmp_path):
    biz = _write(
        tmp_path,
        """
        target: unknown
        answers:
          L1.Q1: maybe
        """,
    )
    result = cr.check(biz)
    l1 = next(l for l in result.layers if l.id == "L1")
    assert "L1.Q1" in l1.unknown_ids


def test_overlay_added_question_is_scored(tmp_path):
    overlay = _write(
        tmp_path,
        """
        extends: four-layer-delegation-readiness
        add:
          - id: "L1.NEW_Q"
            text: x
            weight: 1.0
        """,
        name="overlay.yaml",
    )
    biz = tmp_path / "biz.yaml"
    biz.write_text(yaml.safe_dump({"target": "with-overlay", "answers": _all_yes_answers()}))

    # Without overlay -> PASS
    result_no = cr.check(biz)
    assert result_no.conclusion == "PASS"
    # With overlay -> L1.NEW_Q is unknown -> REVISE or BLOCK
    result_ov = cr.check(biz, overlay_paths=[overlay])
    l1 = next(l for l in result_ov.layers if l.id == "L1")
    assert "L1.NEW_Q" in l1.unknown_ids


def test_overlay_error_propagates(tmp_path):
    overlay = _write(
        tmp_path,
        """
        extends: wrong-name
        """,
        name="overlay.yaml",
    )
    biz = _write(
        tmp_path,
        """
        target: x
        answers: {}
        """,
        name="biz.yaml",
    )
    with pytest.raises(cr.OverlayError):
        cr.check(biz, overlay_paths=[overlay])


# --- organization axis (parallel, non-gating) --------------------------------

def test_axis_role_classification():
    # explicit role wins
    assert cr.axis_role("organization", {"role": "parallel"}) == cr.ROLE_PARALLEL
    assert cr.axis_role("X", {"role": "gating"}) == cr.ROLE_GATING
    # unset -> gating, except historically-parallel efficacy
    assert cr.axis_role("L1", {}) == cr.ROLE_GATING
    assert cr.axis_role("efficacy", {}) == cr.ROLE_PARALLEL


def test_axis_role_unknown_value_is_loud_error():
    """A role typo must not silently demote a parallel axis to a gating layer."""
    with pytest.raises(ValueError):
        cr.axis_role("organization", {"role": "paralell"})


def test_unknown_role_in_definition_surfaces_on_check(tmp_path):
    defn = _write(
        tmp_path,
        """
        version: 1
        name: four-layer-delegation-readiness
        separator: "."
        items:
          - {id: "L1", name: l1, pass: 1.0, revise: 0.5}
          - {id: "L1.Q1", text: q, weight: 1.0}
          - {id: "org", name: org, role: paralell, pass: 1.0, revise: 0.5}
          - {id: "org.C1", text: c, weight: 1.0}
        """,
        name="defn.yaml",
    )
    biz = _write(tmp_path, "target: x\nanswers: {L1.Q1: yes, org.C1: yes}\n")
    with pytest.raises(ValueError):
        cr.check(biz, definition_path=defn)


def test_organization_is_parallel_not_gating():
    """organization BLOCK must not gate the layers (blocked_from stays None)."""
    result = cr.check(ajinomoto_discovery_team_path())
    assert result.conclusion == "BLOCK"
    assert result.blocked_from is None  # all gating layers pass
    layer_ids = {l.id for l in result.layers}
    assert layer_ids == {"L1", "L2", "L3", "L4"}  # organization is NOT a gating layer
    org = next(a for a in result.parallel_axes if a.id == "organization")
    assert org.verdict == "block"
    assert {a.id for a in result.parallel_axes} == {"efficacy", "organization"}


def test_empty_parallel_axis_is_skipped(tmp_path):
    """A parallel axis with zero leaves is unassessed, not a silent BLOCK."""
    defn = _write(
        tmp_path,
        """
        version: 1
        name: four-layer-delegation-readiness
        separator: "."
        items:
          - {id: "L1", name: l1, pass: 1.0, revise: 0.5}
          - {id: "L1.Q1", text: q, weight: 1.0}
          - {id: "org", name: org, role: parallel, pass: 1.0, revise: 0.5}
        """,
        name="defn.yaml",
    )
    biz = _write(tmp_path, "target: x\nanswers: {L1.Q1: yes}\n")
    result = cr.check(biz, definition_path=defn)
    assert result.conclusion == "PASS"  # empty org axis skipped, not blocking
    assert {a.id for a in result.parallel_axes} == set()


def test_organization_overlay_strengthen_and_add(tmp_path):
    """add/strengthen work on the organization axis just like on efficacy."""
    overlay = _write(
        tmp_path,
        """
        extends: four-layer-delegation-readiness
        add:
          - id: "organization.NEW_C"
            text: extra org question
            weight: 1.0
        strengthen:
          "organization": {revise: 0.83}
        """,
        name="overlay.yaml",
    )
    result = cr.check(ajinomoto_discovery_team_path(), overlay_paths=[overlay])
    org = next(a for a in result.parallel_axes if a.id == "organization")
    assert "organization.NEW_C" in org.unknown_ids  # added question is scored


# --- high-stakes domain overlay (examples/overlays/high-stakes-domain) ------

def _hs_overlay_path():
    from conftest import hs_overlay_four_layer_path
    return hs_overlay_four_layer_path()


def _merged_all_yes_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_hs_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def test_high_stakes_all_yes_passes(tmp_path):
    """4/4 on L5 (and all other layers) -> PASS."""
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "hs-all-yes", "answers": _merged_all_yes_answers()}))
    result = cr.check(biz_path, overlay_paths=[_hs_overlay_path()])
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


def test_high_stakes_single_no_blocks(tmp_path):
    """The L5 gate has no revise band: 3/4 -> BLOCK, not REVISE."""
    answers = _merged_all_yes_answers()
    answers["L5.Q4"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "hs-one-no", "answers": answers}))
    result = cr.check(biz_path, overlay_paths=[_hs_overlay_path()])
    assert result.conclusion == "BLOCK"
    assert result.blocked_from == "L5"
    l5 = next(layer for layer in result.layers if layer.id == "L5")
    assert l5.verdict == "block"


def test_sample_ip_business_blocks_at_l5():
    """The bundled IP sample: process layers pass, the prerequisite gate blocks."""
    from conftest import sample_ip_business_path
    result = cr.check(sample_ip_business_path(), overlay_paths=[_hs_overlay_path()])
    verdicts = {layer.id: layer.verdict for layer in result.layers}
    assert verdicts == {"L1": "pass", "L2": "pass", "L3": "pass", "L4": "pass", "L5": "block"}
    assert result.conclusion == "BLOCK"
    assert result.blocked_from == "L5"


# --- insourcing-judgment overlay (examples/overlays/insourcing-judgment) -----
# L_insourcing is a PARALLEL axis: it is scored alongside efficacy/organization
# and never gates L1-L4. pass 1.0 / revise 0.8 over 5 equal-weight questions ->
# 5/5 PASS, 4/5 REVISE, <=3/5 BLOCK. These fix each boundary individually.

def _insourcing_overlay_path():
    from conftest import insourcing_overlay_path
    return insourcing_overlay_path()


def _merged_all_yes_insourcing_answers() -> dict:
    base = yaml.safe_load(four_layer_path().read_text())
    merged = ov.apply_overlays(base, [_insourcing_overlay_path()]).merged
    sep = ov.separator_of(merged)
    return {item["id"]: "yes" for item in merged["items"] if ov.is_leaf(item["id"], sep)}


def _insourcing_axis(result):
    return next(a for a in result.parallel_axes if a.id == "L_insourcing")


def test_insourcing_all_yes_passes(tmp_path):
    """5/5 on L_insourcing (and all other axes) -> PASS."""
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-all-yes", "answers": _merged_all_yes_insourcing_answers()}))
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    axis = _insourcing_axis(result)
    assert axis.verdict == "pass" and axis.score == 1.0
    assert result.conclusion == "PASS"
    assert result.blocked_from is None


def test_insourcing_single_no_revises_without_gating(tmp_path):
    """4/5 (one missing owner) -> the axis REVISEs but does NOT gate L1-L4."""
    answers = _merged_all_yes_insourcing_answers()
    answers["L_insourcing.I2"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-one-no", "answers": answers}))
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    axis = _insourcing_axis(result)
    assert axis.verdict == "revise" and axis.score == 0.8
    assert result.conclusion == "REVISE"
    # parallel axis: every gating layer still passes, so no first gate to fix
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_insourcing_two_no_blocks_without_gating(tmp_path):
    """3/5 -> the axis BLOCKs but still does NOT gate L1-L4 (parallel)."""
    answers = _merged_all_yes_insourcing_answers()
    answers["L_insourcing.I0"] = "no"
    answers["L_insourcing.I1"] = "no"
    biz_path = tmp_path / "biz.yaml"
    biz_path.write_text(yaml.safe_dump({"target": "ins-two-no", "answers": answers}))
    result = cr.check(biz_path, overlay_paths=[_insourcing_overlay_path()])
    axis = _insourcing_axis(result)
    assert axis.verdict == "block" and axis.score == 0.6
    assert result.conclusion == "BLOCK"
    # even at BLOCK the parallel axis does not become a gate
    assert all(layer.verdict == "pass" for layer in result.layers)
    assert result.blocked_from is None


def test_sample_insourcing_business_revises():
    """The bundled sample: process + organization pass, L_insourcing REVISEs (I2)."""
    from conftest import sample_insourcing_business_path
    result = cr.check(sample_insourcing_business_path(), overlay_paths=[_insourcing_overlay_path()])
    assert all(layer.verdict == "pass" for layer in result.layers)
    axis = _insourcing_axis(result)
    assert axis.verdict == "revise"
    assert axis.no_ids == ["L_insourcing.I2"]
    assert result.conclusion == "REVISE"
    assert result.blocked_from is None
