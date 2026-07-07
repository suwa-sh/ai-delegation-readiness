"""Golden regression: the canonical-model migration must not change scoring.

Captured from the pre-migration (old nested-DSL) `aidr check-readiness` /
`aidr score-delegation` runs against the bundled example inputs, before
`src/adr/overlay.py` and `definitions/*.yaml` were rewritten to the flat
canonical model. Question/axis ids changed shape (e.g. ``L1Q1`` -> ``L1.Q1``,
``V1`` -> ``verifiability.V1``) as part of the migration, so this asserts on
scores/verdicts/regions (the end-to-end scoring result), not on exact id
spellings or internal dict shape.
"""
from __future__ import annotations

from adr import check_readiness as cr
from adr import score_delegation as sd
from conftest import sample_business_path, sample_judgments_path

GOLDEN_CHECK_READINESS = {
    "conclusion": "BLOCK",
    "blocked_from": "L1",
    "layers": {
        "L1": {"verdict": "revise", "score": 0.75},
        "L2": {"verdict": "block", "score": 1 / 3},
        "L3": {"verdict": "revise", "score": 0.75},
        "L4": {"verdict": "block", "score": 0.0},
    },
    "parallel_axes": {
        # The sample business provides no organization answers, so that axis is
        # all-unknown -> score 0.0 -> block. efficacy is unchanged by the axis change.
        "efficacy": {"verdict": "revise", "score": 0.75},
        "organization": {"verdict": "block", "score": 0.0},
    },
}

GOLDEN_SCORE_DELEGATION = {
    "receipt_mandatory_items_check": {
        "region": "green",
        "axes": {"verifiability": ("high", 3), "answer_definability": ("high", 3)},
    },
    "invoice_scheme_compliance": {
        "region": "green",
        "axes": {"verifiability": ("high", 3), "answer_definability": ("high", 3)},
    },
    "entertainment_expense_judgment": {
        "region": "green",
        "axes": {"verifiability": ("high", 2), "answer_definability": ("high", 2)},
    },
    "new_hire_decision": {
        "region": "red",
        "axes": {"verifiability": ("low", 0), "answer_definability": ("low", 0)},
    },
    "discriminatory_language_detection": {
        "region": "yellow",
        "axes": {"verifiability": ("high", 2), "answer_definability": ("low", 1)},
    },
}


def test_golden_check_readiness_sample_business():
    result = cr.check(sample_business_path())
    assert result.conclusion == GOLDEN_CHECK_READINESS["conclusion"]
    assert result.blocked_from == GOLDEN_CHECK_READINESS["blocked_from"]
    for layer in result.layers:
        expected = GOLDEN_CHECK_READINESS["layers"][layer.id]
        assert layer.verdict == expected["verdict"], layer.id
        assert layer.score == expected["score"], layer.id
    by_axis = {a.id: a for a in result.parallel_axes}
    assert set(by_axis) == set(GOLDEN_CHECK_READINESS["parallel_axes"])
    for axis_id, expected in GOLDEN_CHECK_READINESS["parallel_axes"].items():
        assert by_axis[axis_id].verdict == expected["verdict"], axis_id
        assert by_axis[axis_id].score == expected["score"], axis_id


def test_golden_score_delegation_sample_judgments():
    result = sd.score(sample_judgments_path())
    by_id = {j.id: j for j in result.judgments}
    assert set(by_id) == set(GOLDEN_SCORE_DELEGATION)
    for jid, expected in GOLDEN_SCORE_DELEGATION.items():
        judgment = by_id[jid]
        assert judgment.region == expected["region"], jid
        for axis_id, (level, score) in expected["axes"].items():
            axis = judgment.axes[axis_id]
            assert axis.level == level, f"{jid}.{axis_id}"
            assert axis.score == score, f"{jid}.{axis_id}"
