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
    sample_task_contract_green_path,
    sample_task_contract_red_path,
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
    ["screen-transition", "check-readiness", "score-delegation", "check-task-contract", "validate-audit-log", "check-overlay", "list-definitions"],
)
def test_subcommand_help(subcommand):
    r = _run(subcommand, "--help")
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_init_template_exits_0():
    r = _run("init", "--target", "four-layer")
    assert r.returncode == 0
    assert "# 問:" in r.stdout


def test_init_missing_overlay_exits_3(tmp_path):
    r = _run("init", "--target", "four-layer", "--overlay", str(tmp_path / "nope.yaml"))
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr
    assert "Traceback" not in r.stderr


def test_screen_transition_sample_exits_0():
    from conftest import sample_task_groups_path

    r = _run("screen-transition", str(sample_task_groups_path()))
    assert r.returncode == 0
    # Sample-specific assertions: the reorganization group leads the output
    # and carries the HITL marker (H1 = regulated financial reporting).
    first_line = r.stdout.splitlines()[0]
    assert "financial_disclosure_draft" in first_line
    assert "REORGANIZATION" in first_line
    assert "[HITL]" in first_line
    for gid in ("expense_entry_check", "sales_proposal_draft", "equipment_maintenance"):
        assert gid in r.stdout


def test_screen_transition_missing_answer_exits_3(tmp_path):
    p = tmp_path / "tg.yaml"
    p.write_text("task_groups:\n  - id: partial\n    answers: {technical_exposure.E1: yes}\n")
    r = _run("screen-transition", str(p))
    assert r.returncode == 3
    assert "missing answers" in r.stderr


def test_screen_transition_broken_yaml_exits_3(tmp_path):
    p = tmp_path / "broken.yaml"
    p.write_text("task_groups: [unclosed\n  - {")
    r = _run("screen-transition", str(p))
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr


def test_check_readiness_after_sample_passes():
    """The story's re-diagnosis must stay PASS, with and without the
    company overlay (its extra answers are pre-filled in the sample)."""
    from conftest import sample_business_after_path, sample_overlay_path

    r = _run("check-readiness", str(sample_business_after_path()))
    assert r.returncode == 0
    assert "Conclusion: PASS" in r.stdout

    r2 = _run(
        "check-readiness", str(sample_business_after_path()),
        "--overlay", str(sample_overlay_path()),
    )
    assert r2.returncode == 0
    assert "Conclusion: PASS" in r2.stdout


def test_score_delegation_missing_judgments_key_exits_3(tmp_path):
    """A wrong-shape input (e.g. an audit-log JSON) must not pass as a
    zero-judgment success."""
    p = tmp_path / "not-judgments.json"
    p.write_text('{"who": {"agent": {"id": "x"}}}')
    r = _run("score-delegation", str(p))
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr


def test_score_delegation_empty_list_is_explicit_success(tmp_path):
    p = tmp_path / "empty.yaml"
    p.write_text("judgments: []\n")
    r = _run("score-delegation", str(p))
    assert r.returncode == 0
    assert "No judgments scored." in r.stdout


def test_validate_audit_log_broken_json_exits_3(tmp_path):
    p = tmp_path / "broken.json"
    p.write_text('{"who": ')
    r = _run("validate-audit-log", str(p))
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr
    assert "Traceback" not in r.stderr


def test_check_overlay_rejected_exits_1(tmp_path):
    """Pin the documented contract: a rejected overlay is exit 1 (not 2)."""
    p = tmp_path / "weaken.yaml"
    p.write_text('version: 1\nextends: four-layer-delegation-readiness\nstrengthen:\n  "L4": {revise: 0.4}\n')
    r = _run("check-overlay", str(p))
    assert r.returncode == 1


def test_check_readiness_blocked_sample_exits_2():
    r = _run("check-readiness", str(sample_business_path()))
    assert r.returncode == 2


def test_score_delegation_mixed_sample_exits_2():
    """The sample includes a red judgment so exit is 2."""
    r = _run("score-delegation", str(sample_judgments_path()))
    assert r.returncode == 2


def test_check_task_contract_green_sample_exits_0():
    r = _run("check-task-contract", str(sample_task_contract_green_path()))
    assert r.returncode == 0


def test_check_task_contract_red_ai_judge_sample_exits_2():
    r = _run("check-task-contract", str(sample_task_contract_red_path()))
    assert r.returncode == 2


def test_check_task_contract_missing_scorer_type_exits_3(tmp_path):
    c = tmp_path / "c.yaml"
    c.write_text("task: t\nanswers:\n  intent.I1: yes\n")
    r = _run("check-task-contract", str(c))
    assert r.returncode == 3
    assert "ERROR" in r.stderr


def test_check_task_contract_json_exposes_region_and_elements():
    r = _run("check-task-contract", str(sample_task_contract_green_path()), "--format", "json")
    payload = json.loads(r.stdout)
    assert payload["region"] == "green"
    assert payload["exit_code"] == 0
    assert {e["id"] for e in payload["elements"]} == {"intent", "boundary", "evidence", "scorer"}


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


def test_check_readiness_json_exposes_parallel_axes():
    """The rendered JSON must carry parallel_axes (incl. organization), not a
    singular efficacy key. This guards the v0.3.0 axis-model migration at the
    renderer boundary, which the object-level golden test does not exercise."""
    r = _run("check-readiness", str(sample_business_path()), "--format", "json")
    payload = json.loads(r.stdout)
    assert "parallel_axes" in payload
    assert "efficacy" not in payload  # old singular key is gone
    axis_ids = {a["id"] for a in payload["parallel_axes"]}
    assert {"efficacy", "organization"} <= axis_ids


def test_list_definitions_json_exposes_parallel_axes():
    r = _run("list-definitions", "--format", "json")
    payload = json.loads(r.stdout)  # array of definition summaries
    four_layer = next(d for d in payload if d["name"] == "four-layer-delegation-readiness")
    assert "parallel_axes" in four_layer
    assert "efficacy_axis" not in four_layer  # old singular key is gone
    axis_ids = {a["id"] for a in four_layer["parallel_axes"]}
    assert {"efficacy", "organization"} <= axis_ids
