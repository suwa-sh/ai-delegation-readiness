"""Audit log JSON Schema validation tests.

Cover the Codex review's P1-2 (format_checker must validate date-time)
and the schema's two-tier minimum/extended structure.
"""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from adr import validate_audit_log as v
from conftest import sample_audit_log_path


def _good_log() -> dict:
    return json.loads(sample_audit_log_path().read_text(encoding="utf-8"))


@pytest.fixture
def good_log_path(tmp_path):
    path = tmp_path / "log.json"
    path.write_text(json.dumps(_good_log()))
    return path


def _write(tmp_path, data, name="log.json"):
    p = tmp_path / name
    p.write_text(json.dumps(data))
    return p


def test_sample_log_passes_minimum(good_log_path):
    result = v.validate(good_log_path, level="minimum")
    assert result.ok, [vio.message for vio in result.violations]


def test_sample_log_passes_extended(good_log_path):
    result = v.validate(good_log_path, level="extended")
    assert result.ok, [vio.message for vio in result.violations]


def test_invalid_date_time_is_rejected_at_extended(tmp_path):
    data = _good_log()
    data["when"] = "not-a-date"
    p = _write(tmp_path, data)
    result = v.validate(p, level="extended")
    assert not result.ok
    messages = " ".join(vio.message for vio in result.violations)
    assert "date-time" in messages


def test_decision_outside_enum_is_rejected_at_extended(tmp_path):
    data = _good_log()
    data["result"]["decision"] = "kinda-maybe-approved"
    p = _write(tmp_path, data)
    result = v.validate(p, level="extended")
    assert not result.ok


def test_decision_outside_enum_is_accepted_at_minimum(tmp_path):
    """Minimum level is intentionally lax on the decision string."""
    data = _good_log()
    data["result"]["decision"] = "kinda-maybe-approved"
    p = _write(tmp_path, data)
    result = v.validate(p, level="minimum")
    assert result.ok


def test_missing_human_delegator_is_rejected_at_minimum(tmp_path):
    """Even at the minimum level the human delegator is required."""
    data = _good_log()
    del data["who"]["human_delegator"]
    p = _write(tmp_path, data)
    result = v.validate(p, level="minimum")
    assert not result.ok


def test_escalated_without_escalated_to_is_rejected_at_extended(tmp_path):
    data = _good_log()
    data["result"]["decision"] = "escalated"
    data["result"].pop("escalated_to", None)
    p = _write(tmp_path, data)
    result = v.validate(p, level="extended")
    assert not result.ok


def test_extended_requires_rule_version(tmp_path):
    data = _good_log()
    for ref in data["why"]["rule_refs"]:
        ref.pop("version", None)
    p = _write(tmp_path, data)
    result = v.validate(p, level="extended")
    assert not result.ok
    messages = " ".join(vio.message for vio in result.violations)
    assert "version" in messages


def test_unknown_level_raises(tmp_path, good_log_path):
    with pytest.raises(ValueError):
        v.validate(good_log_path, level="superextended")
