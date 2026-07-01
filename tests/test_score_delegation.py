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
