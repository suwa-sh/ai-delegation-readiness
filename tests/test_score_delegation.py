"""Delegation matrix scoring tests."""
from __future__ import annotations

import textwrap

import pytest
import yaml

from adr import score_delegation as sd
from conftest import sample_judgments_path


def _write(tmp_path, text, name="j.yaml"):
    p = tmp_path / name
    p.write_text(textwrap.dedent(text))
    return p


def test_score_サンプル判定ファイルを読み込んだ場合_各判定が期待どおりのregionに分類されること():
    # Act
    result = sd.score(sample_judgments_path())
    by_id = {j.id: j.region for j in result.judgments}

    # Assert
    assert by_id["receipt_mandatory_items_check"] == "green"
    assert by_id["invoice_scheme_compliance"] == "green"
    assert by_id["entertainment_expense_judgment"] == "green"
    assert by_id["new_hire_decision"] == "red"
    assert by_id["discriminatory_language_detection"] == "yellow"


def test_score_各軸で3件中2件がyesの場合_greenに分類されること(tmp_path):
    """Axes use binary majority thresholds, not unanimity - a single per-axis 'no' still counts as high."""
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: boundary
            description: 2/3 each axis
            answers:
              verifiability.V1: yes
              verifiability.V2: yes
              verifiability.V3: no
              answer_definability.A1: yes
              answer_definability.A2: yes
              answer_definability.A3: no
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert len(result.judgments) == 1
    assert result.judgments[0].region == "green"


def test_score_両軸とも低い場合_redに分類されること(tmp_path):
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: red_one
            description: all no
            answers: {}
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert result.judgments[0].region == "red"


def test_score_verifiabilityのみ高い場合_yellowに分類されること(tmp_path):
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: high_low
            description: V all yes, A all no
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes }
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert result.judgments[0].region == "yellow"


def test_score_red判定が1件でも含まれる場合_conclusion_exit_codeが2になること(tmp_path):
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: g
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes, answer_definability.A1: yes, answer_definability.A2: yes, answer_definability.A3: yes }
          - id: r
            answers: {}
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert result.conclusion_exit_code == 2


def test_score_yellow判定のみの場合_conclusion_exit_codeが1になること(tmp_path):
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: y
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes }
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert result.conclusion_exit_code == 1


def test_score_green判定のみの場合_conclusion_exit_codeが0になること(tmp_path):
    # Arrange
    j = _write(
        tmp_path,
        """
        judgments:
          - id: g
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes, answer_definability.A1: yes, answer_definability.A2: yes, answer_definability.A3: yes }
        """,
    )

    # Act
    result = sd.score(j)

    # Assert
    assert result.conclusion_exit_code == 0


# --- high-stakes domain overlay (examples/overlays/high-stakes-domain) ------

def _hs_matrix_overlay_path():
    from conftest import hs_overlay_matrix_path
    return hs_overlay_matrix_path()


def _ip_judgments_path():
    from conftest import sample_ip_judgments_path
    return sample_ip_judgments_path()


def test_score_overlayなしでbase閾値の場合_全件greenになること():
    """Base thresholds are majority-only (2/3), lenient enough that every patent-work step clears both axes."""
    # Act
    result = sd.score(_ip_judgments_path())

    # Assert
    assert {j.region for j in result.judgments} == {"green"}


def test_score_high_stakes_overlayで閾値を強化した場合_項目ごとにregionが変わること():
    """The overlay tightens both axes to unanimity (3/3), so only the step with full agreement stays green."""
    # Act
    result = sd.score(_ip_judgments_path(), overlay_paths=[_hs_matrix_overlay_path()])
    by_id = {j.id: j.region for j in result.judgments}

    # Assert
    assert by_id == {
        "patent_classification": "green",
        "prior_art_candidate_retrieval": "yellow",
        "patent_spec_draft": "yellow",
        "invalidity_search_final": "red",
    }


def _region_for(v_high: bool, a_high: bool) -> str:
    if v_high and a_high:
        return "green"
    if v_high or a_high:
        return "yellow"
    return "red"


def _merged_matrix_with_hs_overlay() -> dict:
    import overlay_scoring as ov
    from conftest import matrix_path
    base = ov.load_yaml(matrix_path())
    r = ov.apply_overlays(base, [_hs_matrix_overlay_path()])
    assert r.ok, r.violations
    return r.merged


# Base worked examples whose stored region (computed under base thresholds 2/3)
# lands in a stricter region when re-read under the overlay thresholds (3/3).
# Overlays cannot rewrite existing items, so this divergence is intentional and
# pinned here; docs/07 documents how to read it.
_EXPECTED_STALE_BASE_EXAMPLES = {
    "examples.entertainment_expense_determination": ("green", "red"),
    "examples.coding_mechanical_refactor": ("green", "yellow"),
    "examples.discriminatory_expression_detection": ("yellow", "red"),
    "examples.expense_account_code_suggestion": ("yellow", "red"),
}

_HS_EXAMPLE_IDS = {
    "examples.patent_classification",
    "examples.prior_art_candidate_retrieval",
    "examples.patent_spec_draft",
    "examples.invalidity_search_final",
}


def test_apply_overlays_high_stakesを適用した場合_examplesのregionが閾値通りでbase乖離が既知集合と一致すること():
    # Act
    merged = _merged_matrix_with_hs_overlay()
    thresholds = {
        i["id"]: i["threshold"]
        for i in merged["items"]
        if i["id"] in ("verifiability", "answer_definability")
    }

    # Assert
    stale: dict[str, tuple[str, str]] = {}
    for item in merged["items"]:
        if "verifiability_yes" not in item:
            continue  # examples group header or non-scored leaf
        v_high = len(item["verifiability_yes"]) >= thresholds["verifiability"]
        a_high = len(item.get("answer_definability_yes", [])) >= thresholds["answer_definability"]
        recomputed = _region_for(v_high, a_high)
        if item["id"] in _HS_EXAMPLE_IDS:
            # overlay-declared examples must agree with the strengthened thresholds
            assert item["region"] == recomputed, item["id"]
        elif item["region"] != recomputed:
            stale[item["id"]] = (item["region"], recomputed)
    assert stale == _EXPECTED_STALE_BASE_EXAMPLES
