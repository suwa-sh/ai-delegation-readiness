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


def test_sample_judgments_produce_expected_regions():
    result = sd.score(sample_judgments_path())
    by_id = {j.id: j.region for j in result.judgments}
    assert by_id["receipt_mandatory_items_check"] == "green"
    assert by_id["invoice_scheme_compliance"] == "green"
    assert by_id["entertainment_expense_judgment"] == "green"
    assert by_id["new_hire_decision"] == "red"
    assert by_id["discriminatory_language_detection"] == "yellow"


def test_boundary_high_axis(tmp_path):
    """2/3 Yes on each axis -> still high (binary majority)."""
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
    result = sd.score(j)
    assert len(result.judgments) == 1
    assert result.judgments[0].region == "green"


def test_low_x_low_is_red(tmp_path):
    j = _write(
        tmp_path,
        """
        judgments:
          - id: red_one
            description: all no
            answers: {}
        """,
    )
    result = sd.score(j)
    assert result.judgments[0].region == "red"


def test_mixed_axis_is_yellow(tmp_path):
    j = _write(
        tmp_path,
        """
        judgments:
          - id: high_low
            description: V all yes, A all no
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes }
        """,
    )
    result = sd.score(j)
    assert result.judgments[0].region == "yellow"


def test_exit_code_2_when_any_red(tmp_path):
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
    result = sd.score(j)
    assert result.conclusion_exit_code == 2


def test_exit_code_1_when_only_yellows(tmp_path):
    j = _write(
        tmp_path,
        """
        judgments:
          - id: y
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes }
        """,
    )
    result = sd.score(j)
    assert result.conclusion_exit_code == 1


def test_exit_code_0_when_only_greens(tmp_path):
    j = _write(
        tmp_path,
        """
        judgments:
          - id: g
            answers: { verifiability.V1: yes, verifiability.V2: yes, verifiability.V3: yes, answer_definability.A1: yes, answer_definability.A2: yes, answer_definability.A3: yes }
        """,
    )
    result = sd.score(j)
    assert result.conclusion_exit_code == 0


# --- high-stakes domain overlay (examples/overlays/high-stakes-domain) ------

def _hs_matrix_overlay_path():
    from conftest import hs_overlay_matrix_path
    return hs_overlay_matrix_path()


def _ip_judgments_path():
    from conftest import sample_ip_judgments_path
    return sample_ip_judgments_path()


def test_sample_ip_judgments_without_overlay_all_green():
    """Under base thresholds (2/3), every patent-work step scores green."""
    result = sd.score(_ip_judgments_path())
    assert {j.region for j in result.judgments} == {"green"}


def test_sample_ip_judgments_with_overlay_regions():
    """Under strengthened thresholds (3/3), only classification stays green."""
    result = sd.score(_ip_judgments_path(), overlay_paths=[_hs_matrix_overlay_path()])
    by_id = {j.id: j.region for j in result.judgments}
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


def test_high_stakes_examples_consistent_and_base_divergence_pinned():
    merged = _merged_matrix_with_hs_overlay()
    thresholds = {
        i["id"]: i["threshold"]
        for i in merged["items"]
        if i["id"] in ("verifiability", "answer_definability")
    }
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
