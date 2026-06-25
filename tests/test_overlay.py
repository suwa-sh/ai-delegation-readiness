"""Overlay merge rule tests.

Cover the boundary conditions called out in the Codex review:
- extends mismatch
- add: unknown id, id collision (against base AND within same overlay)
- strengthen: weakening rejected, equal threshold accepted
- efficacy_axis: add_questions and strengthen_thresholds
- unsupported overlay key at top level / per-layer
- empty list / empty mapping no-op safety
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from adr import overlay as ov
from conftest import four_layer_path


def _yaml(text: str) -> dict:
    return yaml.safe_load(textwrap.dedent(text))


def _base() -> dict:
    return ov.load_yaml(four_layer_path())


def test_extends_mismatch_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: wrong-name
        layers:
          - id: L1
            add_questions: []
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    kinds = {v.kind for v in result.violations}
    assert "extends_mismatch" in kinds


def test_add_question_to_known_layer():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            add_questions:
              - id: NEW1
                text: extra question
                weight: 1.0
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert result.ok
    l1 = next(l for l in result.merged["layers"] if l["id"] == "L1")
    assert any(q["id"] == "NEW1" for q in l1["questions"])


def test_add_question_with_unknown_layer_id_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L99
            add_questions:
              - id: NEW1
                text: x
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "unknown_id" for v in result.violations)


def test_add_question_id_collision_with_base_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            add_questions:
              - id: L1Q1
                text: collides with base
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "id_collision" for v in result.violations)


def test_add_question_id_collision_within_same_overlay_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            add_questions:
              - id: DUP
                text: first
              - id: DUP
                text: second
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "id_collision" for v in result.violations)


def test_strengthen_threshold_higher_is_accepted():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            strengthen_thresholds:
              revise: 0.8
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert result.ok
    l1 = next(l for l in result.merged["layers"] if l["id"] == "L1")
    assert l1["verdict_thresholds"]["revise"] == 0.8


def test_strengthen_threshold_equal_is_accepted():
    base = _base()
    # base L1 revise is 0.5
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            strengthen_thresholds:
              revise: 0.5
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert result.ok


def test_strengthen_threshold_weakening_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers:
          - id: L1
            strengthen_thresholds:
              revise: 0.3
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "weakening_rejected" for v in result.violations)


def test_efficacy_axis_add_questions_and_strengthen_works():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        efficacy_axis:
          add_questions:
            - id: E_NEW
              text: extra efficacy question
          strengthen_thresholds:
            revise: 0.9
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert result.ok
    eff = result.merged["efficacy_axis"]
    assert any(q["id"] == "E_NEW" for q in eff["questions"])
    assert eff["verdict_thresholds"]["revise"] == 0.9


def test_efficacy_axis_unsupported_op_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        efficacy_axis:
          rename_questions: {}
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "unsupported_op" for v in result.violations)


def test_unsupported_top_level_key_is_rejected():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        rename_layers: {}
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert not result.ok
    assert any(v.kind == "unsupported_op" for v in result.violations)


def test_empty_layers_overlay_is_no_op():
    base = _base()
    overlay = _yaml(
        """
        version: 1
        extends: four-layer-delegation-readiness
        layers: []
        """
    )
    result = ov.apply_overlay(base, overlay)
    assert result.ok
    # base preserved
    assert len(result.merged["layers"]) == len(base["layers"])
