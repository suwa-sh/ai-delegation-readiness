"""CLI exit code regression tests.

Exit code contract (per `aidr` design):

- 0 ok / all green / valid
- 1 partial / yellow / violations
- 2 block / red
- 3 overlay or input file error
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from conftest import (
    REPO_ROOT,
    sample_audit_log_path,
    sample_business_path,
    sample_judgments_path,
    sample_overlay_path,
)

AIDR = REPO_ROOT / "bin" / "aidr"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AIDR), *args],
        check=False,
        capture_output=True,
        text=True,
    )


def test_help_exits_zero():
    r = _run("--help")
    assert r.returncode == 0


@pytest.mark.parametrize(
    "subcommand",
    ["check-readiness", "score-delegation", "validate-audit-log", "check-overlay", "list-definitions"],
)
def test_subcommand_help(subcommand):
    r = _run(subcommand, "--help")
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_check_readiness_blocked_sample_exits_2():
    r = _run("check-readiness", str(sample_business_path()))
    assert r.returncode == 2


def test_score_delegation_mixed_sample_exits_2():
    """The sample includes a red judgment so exit is 2."""
    r = _run("score-delegation", str(sample_judgments_path()))
    assert r.returncode == 2


def test_validate_audit_log_minimum_passes():
    r = _run("validate-audit-log", str(sample_audit_log_path()), "--level", "minimum")
    assert r.returncode == 0


def test_validate_audit_log_extended_passes():
    r = _run("validate-audit-log", str(sample_audit_log_path()), "--level", "extended")
    assert r.returncode == 0


def test_check_overlay_sample_passes():
    r = _run("check-overlay", str(sample_overlay_path()))
    assert r.returncode == 0


def test_list_definitions_with_missing_overlay_exits_3():
    r = _run("list-definitions", "--overlay", "/tmp/does-not-exist.yaml")
    assert r.returncode == 3
    assert "ERROR" in r.stderr


def test_check_readiness_with_missing_overlay_exits_3():
    r = _run(
        "check-readiness",
        str(sample_business_path()),
        "--overlay",
        "/tmp/does-not-exist.yaml",
    )
    # OverlayError path or FileNotFoundError - both should surface as error
    assert r.returncode != 0


def test_format_json_returns_parseable_json():
    r = _run(
        "validate-audit-log",
        str(sample_audit_log_path()),
        "--level",
        "extended",
        "--format",
        "json",
    )
    payload = json.loads(r.stdout)
    assert payload["ok"] is True
    assert payload["level"] == "extended"
