"""Overlay merge rule tests for the canonical engine.

Covers add / strengthen (leaf + group, group-scoped), every boundary
condition, source-order preservation, opaque-payload preservation, and a
round-trip against the real four-layer.yaml overlay sample. Also covers
delegation-matrix axes / examples / regions overlay cases that the old
per-DSL tests never exercised.
"""
from __future__ import annotations

from copy import deepcopy

import overlay_scoring as ov
from conftest import four_layer_path, matrix_path, sample_overlay_path


def four_layer() -> dict:
    return ov.load_yaml(four_layer_path())


def matrix() -> dict:
    return ov.load_yaml(matrix_path())


def _ids(defn: dict) -> list[str]:
    return [it["id"] for it in defn["items"]]


# --- base integrity ---------------------------------------------------------

def test_base_definitions_validate():
    assert ov.validate_definition(four_layer()) == []
    assert ov.validate_definition(matrix()) == []


def test_definition_with_orphan_leaf_is_rejected():
    defn = {"version": 1, "name": "x", "items": [{"id": "A.child"}]}
    kinds = {v.kind for v in ov.validate_definition(defn)}
    assert "unknown_group" in kinds


def test_definition_with_duplicate_id_is_rejected():
    defn = {"version": 1, "name": "x", "items": [{"id": "A"}, {"id": "A"}]}
    kinds = {v.kind for v in ov.validate_definition(defn)}
    assert "id_collision" in kinds


# --- add (four-layer) --------------------------------------------------------

def test_add_leaf_to_existing_layer():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q5", "text": "extra", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert r.ok, r.violations
    assert "L1.Q5" in _ids(r.merged)


def test_add_leaf_with_unknown_group_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "LZ.Q1", "text": "x", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    # LZ matches selector "L*" but there is no LZ header
    assert not r.ok
    assert {v.kind for v in r.violations} == {"unknown_group"}


def test_add_to_ungoverned_group_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "XYZ.q", "text": "x"}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_add_id_collision_with_base_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q1", "text": "dup", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"id_collision"}


def test_add_id_collision_within_same_overlay_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.NEW", "text": "a", "weight": 1.0},
                       {"id": "L1.NEW", "text": "b", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"id_collision"}


def test_add_new_layer_header_then_leaf_in_same_overlay():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L5", "name": "extra_layer", "pass": 1.0, "revise": 0.7},
                       {"id": "L5.Q1", "text": "q", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert r.ok, r.violations
    assert "L5" in _ids(r.merged) and "L5.Q1" in _ids(r.merged)


def test_add_id_with_two_separators_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "L1.Q1.deep", "text": "x", "weight": 1.0}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


def test_add_item_without_id_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness", "add": [{"text": "no id"}]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


# --- strengthen (four-layer) -------------------------------------------------

def test_strengthen_group_field_higher_is_accepted():
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.8}}}
    r = ov.apply_overlay(four_layer(), overlay)
    assert r.ok, r.violations
    l4 = next(i for i in r.merged["items"] if i["id"] == "L4")
    assert l4["revise"] == 0.8


def test_strengthen_group_field_equal_is_accepted():
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.6}}}  # base L4 revise is 0.6
    r = ov.apply_overlay(four_layer(), overlay)
    assert r.ok, r.violations


def test_strengthen_group_field_weakening_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": 0.4}}}  # 0.6 -> 0.4 is weaker
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"weakening_rejected"}


def test_strengthen_non_numeric_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L4": {"revise": "soon"}}}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"invalid_overlay"}


def test_strengthen_undeclared_field_is_rejected():
    # weight is a leaf field but not declared strengthen-able in four-layer
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L1.Q1": {"weight": 2.0}}}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_strengthen_unknown_id_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness",
               "strengthen": {"L9": {"revise": 0.9}}}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"unknown_id"}


def test_efficacy_group_add_and_strengthen_works():
    overlay = {"extends": "four-layer-delegation-readiness",
               "add": [{"id": "efficacy.E_NEW", "text": "extra efficacy question", "weight": 1.0}],
               "strengthen": {"efficacy": {"revise": 0.9}}}
    r = ov.apply_overlay(four_layer(), overlay)
    assert r.ok, r.violations
    assert "efficacy.E_NEW" in _ids(r.merged)
    eff = next(i for i in r.merged["items"] if i["id"] == "efficacy")
    assert eff["revise"] == 0.9


# --- top-level / extends ----------------------------------------------------

def test_extends_mismatch_is_rejected():
    overlay = {"extends": "wrong-name", "add": []}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"extends_mismatch"}


def test_unsupported_top_level_key_is_rejected():
    overlay = {"extends": "four-layer-delegation-readiness", "delete": ["L1"]}
    r = ov.apply_overlay(four_layer(), overlay)
    assert {v.kind for v in r.violations} == {"unsupported_op"}


# --- multi-overlay ----------------------------------------------------------

def test_apply_overlays_stops_at_first_bad(tmp_path):
    good = tmp_path / "good.yaml"
    bad = tmp_path / "bad.yaml"
    after = tmp_path / "after.yaml"
    good.write_text("extends: four-layer-delegation-readiness\nadd:\n  - {id: 'L1.G1', text: g, weight: 1.0}\n")
    bad.write_text("extends: four-layer-delegation-readiness\nstrengthen:\n  L4: {revise: 0.1}\n")
    after.write_text("extends: four-layer-delegation-readiness\nadd:\n  - {id: 'L1.G2', text: g, weight: 1.0}\n")
    r = ov.apply_overlays(four_layer(), [good, bad, after])
    assert not r.ok
    assert r.applied == [str(good)]           # good applied, stopped before 'after'
    assert "L1.G1" in _ids(r.merged)
    assert "L1.G2" not in _ids(r.merged)


# --- structural guarantees ---------------------------------------------------

def test_source_order_and_opaque_payload_preserved():
    base = four_layer()
    overlay = ov.load_yaml(sample_overlay_path())
    r = ov.apply_overlay(base, overlay)
    assert r.ok, r.violations
    groups = ov.group_items(r.merged)
    # group order preserved
    assert list(groups.keys()) == ["L1", "L2", "L3", "L4", "efficacy"]
    # added leaves appended to their group, base leaves kept in order
    l1_leaves = [i["id"] for i in groups["L1"]["leaves"]]
    assert l1_leaves == ["L1.Q1", "L1.Q2", "L1.Q3", "L1.Q4", "L1.ACME_Q5"]
    # opaque payload on the header survives untouched
    assert groups["L1"]["header"]["case_evidence"][0]["confidence"] == "observed_fact"


def test_engine_never_mutates_base():
    base = four_layer()
    snapshot = deepcopy(base)
    ov.apply_overlay(base, {"extends": "four-layer-delegation-readiness",
                             "add": [{"id": "L1.Z", "text": "z", "weight": 1.0}]})
    assert base == snapshot


# --- round-trip against the real overlay sample ------------------------------

def test_roundtrip_sample_overlay():
    r = ov.apply_overlay(four_layer(), ov.load_yaml(sample_overlay_path()))
    assert r.ok, r.violations
    ids = _ids(r.merged)
    assert "L1.ACME_Q5" in ids and "L4.ACME_Q6" in ids
    l4 = next(i for i in r.merged["items"] if i["id"] == "L4")
    assert l4["revise"] == 0.8


# --- delegation-matrix: axes / examples / regions ---------------------------
# (not exercised by the old per-DSL overlay tests, which only covered
# four-layer's layers/efficacy_axis)

def test_matrix_add_question_to_axis():
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "verifiability.V4", "text": "extra question"}]}
    r = ov.apply_overlay(matrix(), overlay)
    assert r.ok, r.violations
    assert "verifiability.V4" in _ids(r.merged)


def test_matrix_add_question_to_unknown_axis_is_rejected():
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "novelty.N1", "text": "extra"}]}
    r = ov.apply_overlay(matrix(), overlay)
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_matrix_strengthen_threshold_higher_is_accepted():
    overlay = {"extends": "delegation-matrix",
               "strengthen": {"verifiability": {"threshold": 3}}}
    r = ov.apply_overlay(matrix(), overlay)
    assert r.ok, r.violations
    axis = next(i for i in r.merged["items"] if i["id"] == "verifiability")
    assert axis["threshold"] == 3


def test_matrix_strengthen_threshold_weakening_is_rejected():
    overlay = {"extends": "delegation-matrix",
               "strengthen": {"verifiability": {"threshold": 1}}}  # 2 -> 1 is weaker
    r = ov.apply_overlay(matrix(), overlay)
    assert {v.kind for v in r.violations} == {"weakening_rejected"}


def test_matrix_add_example():
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "examples.acme_custom_check",
                        "judgment": "Acme custom check", "region": "green"}]}
    r = ov.apply_overlay(matrix(), overlay)
    assert r.ok, r.violations
    assert "examples.acme_custom_check" in _ids(r.merged)


def test_matrix_add_to_regions_is_rejected():
    # regions is a fixed lookup, not an extension point: overlays cannot grow it
    overlay = {"extends": "delegation-matrix",
               "add": [{"id": "regions.blue", "when": [], "action": "n/a"}]}
    r = ov.apply_overlay(matrix(), overlay)
    assert {v.kind for v in r.violations} == {"unsupported_op"}


def test_matrix_regions_order_and_opaque_when_preserved():
    groups = ov.group_items(matrix())
    region_ids = [i["id"] for i in groups["regions"]["leaves"]]
    assert region_ids == ["regions.green", "regions.yellow", "regions.red"]
    green = groups["regions"]["leaves"][0]
    assert green["when"] == [{"verifiability": "high", "answer_definability": "high"}]
