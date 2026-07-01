"""4-layer + efficacy readiness scoring tests."""
from __future__ import annotations

import textwrap

import pytest
import yaml

from adr import overlay as ov
from adr import check_readiness as cr
from conftest import sample_business_path, four_layer_path


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
