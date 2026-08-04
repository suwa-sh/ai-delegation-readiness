"""text_ja completeness and overlay-preservation tests.

The overlay engine treats unknown fields as opaque payload, but the existing
opaque test only covers one header's case_evidence. These tests pin the two
guarantees the Japanese question texts rely on:

1. completeness — every question leaf in every definition carries a
   non-empty ``text_ja`` (a single forgotten question would otherwise pass
   all other tests silently).
2. preservation — applying an overlay keeps each leaf's ``text_ja`` intact.
"""
from __future__ import annotations

import pytest

import overlay_scoring as ov
from conftest import (
    four_layer_path,
    hs_overlay_four_layer_path,
    matrix_path,
    patch_decision_path,
    patch_ownership_path,
    risk_architecture_path,
    task_contract_path,
    transition_path,
)

DEFINITIONS = {
    "four-layer": four_layer_path,
    "delegation-matrix": matrix_path,
    "task-contract": task_contract_path,
    "patch-ownership": patch_ownership_path,
    "transition-screening": transition_path,
    "risk-architecture": risk_architecture_path,
}


def _question_leaves(defn: dict) -> list[dict]:
    """Question leaves = items with a ``text`` field scored as questions.

    ``kind`` defaults to "question"; data/lookup leaves (scorer.type,
    gates.*, examples.*) carry no ``text`` or a non-question kind.
    """
    return [
        item
        for item in defn["items"]
        if "text" in item and item.get("kind", "question") == "question"
    ]


@pytest.mark.parametrize(
    "name",
    DEFINITIONS,
    ids=[f"{n}の場合_text_jaが非空であること" for n in DEFINITIONS],
)
def test_question_leaves_全定義の場合_text_jaが非空であること(name):
    # Act
    defn = ov.load_yaml(DEFINITIONS[name]())
    leaves = _question_leaves(defn)

    # Assert
    assert leaves, f"{name}: no question leaves found (parsing broke?)"
    missing = [l["id"] for l in leaves if not str(l.get("text_ja", "")).strip()]
    assert missing == [], f"{name}: question leaves without text_ja: {missing}"


# patch-decision is deliberately excluded from DEFINITIONS above: all of its
# leaves are ``kind: lookup`` (no question leaves), so _question_leaves()
# would find nothing and the shared test would report a false "parsing
# broke?" failure. Its text_ja completeness is pinned separately here, scoped
# to the three groups that actually carry ``text``/``text_ja``
# (decision / discard_reason / reading — bands carries label/label_ja instead).

def _text_ja_leaves(defn: dict, group_prefixes: tuple[str, ...]) -> list[dict]:
    return [
        item
        for item in defn["items"]
        if any(item["id"].startswith(f"{prefix}.") for prefix in group_prefixes)
    ]


def test__text_ja_leaves_patch_decision定義の場合_text_jaが非空であること():
    # Act
    defn = ov.load_yaml(patch_decision_path())
    leaves = _text_ja_leaves(defn, ("decision", "discard_reason", "reading"))

    # Assert
    assert leaves, "patch-decision: no decision/discard_reason/reading leaves found"
    missing = [l["id"] for l in leaves if not str(l.get("text_ja", "")).strip()]
    assert missing == [], f"patch-decision: leaves without text_ja: {missing}"


def test_apply_overlays_hs_overlayを適用した場合_text_jaが保持されること():
    # Arrange
    base = ov.load_yaml(four_layer_path())

    # Act
    result = ov.apply_overlays(base, [hs_overlay_four_layer_path()])

    # Assert
    assert result.ok, result.violations
    base_ja = {l["id"]: l["text_ja"] for l in _question_leaves(base)}
    merged_ja = {
        l["id"]: l.get("text_ja")
        for l in _question_leaves(result.merged)
        if l["id"] in base_ja
    }
    assert merged_ja == base_ja
