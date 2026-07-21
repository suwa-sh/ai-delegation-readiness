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


def test_validate_サンプルログをminimumレベルで検証した場合_okになること(good_log_path):
    # Act
    result = v.validate(good_log_path, level="minimum")

    # Assert
    assert result.ok, [vio.message for vio in result.violations]


def test_validate_サンプルログをextendedレベルで検証した場合_okになること(good_log_path):
    # Act
    result = v.validate(good_log_path, level="extended")

    # Assert
    assert result.ok, [vio.message for vio in result.violations]


def test_validate_whenが不正な日時形式の場合_extendedレベルで拒否されること(tmp_path):
    # Arrange
    data = _good_log()
    data["when"] = "not-a-date"
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="extended")

    # Assert
    assert not result.ok
    messages = " ".join(vio.message for vio in result.violations)
    assert "date-time" in messages


def test_validate_decisionがenum外の値の場合_extendedレベルで拒否されること(tmp_path):
    # Arrange
    data = _good_log()
    data["result"]["decision"] = "kinda-maybe-approved"
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="extended")

    # Assert
    assert not result.ok


def test_validate_decisionがenum外の値の場合_minimumレベルでは許容されること(tmp_path):
    """Minimum level is intentionally lax on the decision string."""
    # Arrange
    data = _good_log()
    data["result"]["decision"] = "kinda-maybe-approved"
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="minimum")

    # Assert
    assert result.ok


def test_validate_human_delegatorが欠落している場合_minimumレベルでも拒否されること(tmp_path):
    """Even at the minimum level the human delegator is required."""
    # Arrange
    data = _good_log()
    del data["who"]["human_delegator"]
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="minimum")

    # Assert
    assert not result.ok


def test_validate_decisionがescalatedでescalated_toが欠落している場合_extendedレベルで拒否されること(tmp_path):
    # Arrange
    data = _good_log()
    data["result"]["decision"] = "escalated"
    data["result"].pop("escalated_to", None)
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="extended")

    # Assert
    assert not result.ok


def test_validate_rule_refsのversionが欠落している場合_extendedレベルで拒否されること(tmp_path):
    # Arrange
    data = _good_log()
    for ref in data["why"]["rule_refs"]:
        ref.pop("version", None)
    p = _write(tmp_path, data)

    # Act
    result = v.validate(p, level="extended")

    # Assert
    assert not result.ok
    messages = " ".join(vio.message for vio in result.violations)
    assert "version" in messages


def test_validate_未知のlevelを指定した場合_ValueErrorが送出されること(tmp_path, good_log_path):
    # Act & Assert
    with pytest.raises(ValueError):
        v.validate(good_log_path, level="superextended")
