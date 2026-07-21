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


def test_aidr_helpオプションを渡した場合_exit0になること():
    # Act
    r = _run("--help")
    # Assert
    assert r.returncode == 0


@pytest.mark.parametrize(
    "subcommand",
    ["screen-transition", "check-readiness", "score-delegation", "check-task-contract", "validate-audit-log", "check-overlay", "list-definitions"],
    ids=[
        "screen_transitionの場合_exit0でusageを含むこと",
        "check_readinessの場合_exit0でusageを含むこと",
        "score_delegationの場合_exit0でusageを含むこと",
        "check_task_contractの場合_exit0でusageを含むこと",
        "validate_audit_logの場合_exit0でusageを含むこと",
        "check_overlayの場合_exit0でusageを含むこと",
        "list_definitionsの場合_exit0でusageを含むこと",
    ],
)
def test_aidr_subcommand_help_helpオプションを渡した場合_exit0でusageを含むこと(subcommand):
    # Act
    r = _run(subcommand, "--help")
    # Assert
    assert r.returncode == 0
    assert "usage" in r.stdout.lower()


def test_aidr_init_four_layerターゲットを渡した場合_exit0で問い文言を出力すること():
    # Act
    r = _run("init", "--target", "four-layer")
    # Assert
    assert r.returncode == 0
    assert "# 問:" in r.stdout


def test_aidr_init_存在しないoverlayを渡した場合_exit3になること(tmp_path):
    # Act
    r = _run("init", "--target", "four-layer", "--overlay", str(tmp_path / "nope.yaml"))
    # Assert
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr
    assert "Traceback" not in r.stderr


def test_aidr_screen_transition_サンプルを渡した場合_exit0で並び順とhitlマーカーが正しいこと():
    # Arrange
    from conftest import sample_task_groups_path

    # Act
    r = _run("screen-transition", str(sample_task_groups_path()))
    # Assert
    assert r.returncode == 0
    # Sample-specific assertions: the reorganization group leads the output
    # and carries the HITL marker (H1 = regulated financial reporting).
    first_line = r.stdout.splitlines()[0]
    assert "financial_disclosure_draft" in first_line
    assert "REORGANIZATION" in first_line
    assert "[HITL]" in first_line
    for gid in ("expense_entry_check", "sales_proposal_draft", "equipment_maintenance"):
        assert gid in r.stdout


def test_aidr_screen_transition_回答が欠けたtask_groupsを渡した場合_exit3になること(tmp_path):
    # Arrange
    p = tmp_path / "tg.yaml"
    p.write_text("task_groups:\n  - id: partial\n    answers: {technical_exposure.E1: yes}\n")
    # Act
    r = _run("screen-transition", str(p))
    # Assert
    assert r.returncode == 3
    assert "missing answers" in r.stderr


def test_aidr_screen_transition_不正なyamlを渡した場合_exit3になること(tmp_path):
    # Arrange
    p = tmp_path / "broken.yaml"
    p.write_text("task_groups: [unclosed\n  - {")
    # Act
    r = _run("screen-transition", str(p))
    # Assert
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr


def test_aidr_check_readiness_再診断後のサンプルを渡した場合_overlay有無に関わらずpassになること():
    """The story's re-diagnosis must stay PASS — plain, and with the company
    overlay (the with-overlay twin carries the extra answers; CSV rejects
    unknown ids, so overlay answers live in a separate file)."""
    # Arrange
    from conftest import (
        sample_business_after_overlay_path,
        sample_business_after_path,
        sample_overlay_path,
    )

    # Act
    r = _run("check-readiness", str(sample_business_after_path()))
    # Assert
    assert r.returncode == 0
    assert "Conclusion: PASS" in r.stdout

    # Act
    r2 = _run(
        "check-readiness", str(sample_business_after_overlay_path()),
        "--overlay", str(sample_overlay_path()),
    )
    # Assert
    assert r2.returncode == 0
    assert "Conclusion: PASS" in r2.stdout


def test_aidr_score_delegation_judgmentsキーがない入力を渡した場合_exit3になること(tmp_path):
    """A wrong-shape input (e.g. an audit-log JSON) must not pass as a
    zero-judgment success."""
    # Arrange
    p = tmp_path / "not-judgments.json"
    p.write_text('{"who": {"agent": {"id": "x"}}}')
    # Act
    r = _run("score-delegation", str(p))
    # Assert
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr


def test_aidr_score_delegation_空のjudgmentsを渡した場合_exit0で成功メッセージになること(tmp_path):
    # Arrange
    p = tmp_path / "empty.yaml"
    p.write_text("judgments: []\n")
    # Act
    r = _run("score-delegation", str(p))
    # Assert
    assert r.returncode == 0
    assert "No judgments scored." in r.stdout


def test_aidr_validate_audit_log_不正なjsonを渡した場合_exit3になること(tmp_path):
    # Arrange
    p = tmp_path / "broken.json"
    p.write_text('{"who": ')
    # Act
    r = _run("validate-audit-log", str(p))
    # Assert
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr
    assert "Traceback" not in r.stderr


def test_aidr_check_overlay_閾値を緩和するoverlayを渡した場合_exit1になること(tmp_path):
    """Pin the documented contract: a rejected overlay is exit 1 (not 2)."""
    # Arrange
    p = tmp_path / "weaken.yaml"
    p.write_text('version: 1\nextends: four-layer-delegation-readiness\nstrengthen:\n  "L4": {revise: 0.4}\n')
    # Act
    r = _run("check-overlay", str(p))
    # Assert
    assert r.returncode == 1


def test_aidr_check_readiness_blockedサンプルを渡した場合_exit2になること():
    # Act
    r = _run("check-readiness", str(sample_business_path()))
    # Assert
    assert r.returncode == 2


def test_aidr_score_delegation_redを含むサンプルを渡した場合_exit2になること():
    """The sample includes a red judgment so exit is 2."""
    # Act
    r = _run("score-delegation", str(sample_judgments_path()))
    # Assert
    assert r.returncode == 2


def test_aidr_check_task_contract_greenサンプルを渡した場合_exit0になること():
    # Act
    r = _run("check-task-contract", str(sample_task_contract_green_path()))
    # Assert
    assert r.returncode == 0


def test_aidr_check_task_contract_red_ai_judgeサンプルを渡した場合_exit2になること():
    # Act
    r = _run("check-task-contract", str(sample_task_contract_red_path()))
    # Assert
    assert r.returncode == 2


def test_aidr_check_task_contract_scorer_typeがない入力を渡した場合_exit3になること(tmp_path):
    # Arrange
    c = tmp_path / "c.yaml"
    c.write_text("task: t\nanswers:\n  intent.I1: yes\n")
    # Act
    r = _run("check-task-contract", str(c))
    # Assert
    assert r.returncode == 3
    assert "ERROR" in r.stderr


def test_aidr_check_task_contract_format_jsonを指定した場合_regionとelementsを含むこと():
    # Act
    r = _run("check-task-contract", str(sample_task_contract_green_path()), "--format", "json")
    payload = json.loads(r.stdout)
    # Assert
    assert payload["region"] == "green"
    assert payload["exit_code"] == 0
    assert {e["id"] for e in payload["elements"]} == {"intent", "boundary", "evidence", "scorer"}


def test_aidr_validate_audit_log_levelにminimumを指定した場合_exit0になること():
    # Act
    r = _run("validate-audit-log", str(sample_audit_log_path()), "--level", "minimum")
    # Assert
    assert r.returncode == 0


def test_aidr_validate_audit_log_levelにextendedを指定した場合_exit0になること():
    # Act
    r = _run("validate-audit-log", str(sample_audit_log_path()), "--level", "extended")
    # Assert
    assert r.returncode == 0


def test_aidr_check_overlay_正当なoverlayサンプルを渡した場合_exit0になること():
    # Act
    r = _run("check-overlay", str(sample_overlay_path()))
    # Assert
    assert r.returncode == 0


def test_aidr_list_definitions_存在しないoverlayを渡した場合_exit3になること():
    # Act
    r = _run("list-definitions", "--overlay", "/tmp/does-not-exist.yaml")
    # Assert
    assert r.returncode == 3
    assert "ERROR" in r.stderr


def test_aidr_check_readiness_存在しないoverlayを渡した場合_exit0以外になること():
    # Act
    r = _run(
        "check-readiness",
        str(sample_business_path()),
        "--overlay",
        "/tmp/does-not-exist.yaml",
    )
    # Assert
    # OverlayError path or FileNotFoundError - both should surface as error
    assert r.returncode != 0


def test_aidr_validate_audit_log_format_jsonを指定した場合_パース可能なjsonでokとlevelを返すこと():
    # Act
    r = _run(
        "validate-audit-log",
        str(sample_audit_log_path()),
        "--level",
        "extended",
        "--format",
        "json",
    )
    payload = json.loads(r.stdout)
    # Assert
    assert payload["ok"] is True
    assert payload["level"] == "extended"


def test_aidr_check_readiness_format_jsonを指定した場合_parallel_axesを含みefficacyキーを含まないこと():
    """The rendered JSON must carry parallel_axes (incl. organization), not a
    singular efficacy key. This guards the v0.3.0 axis-model migration at the
    renderer boundary, which the object-level golden test does not exercise."""
    # Act
    r = _run("check-readiness", str(sample_business_path()), "--format", "json")
    payload = json.loads(r.stdout)
    # Assert
    assert "parallel_axes" in payload
    assert "efficacy" not in payload  # old singular key is gone
    axis_ids = {a["id"] for a in payload["parallel_axes"]}
    assert {"efficacy", "organization"} <= axis_ids


def test_aidr_list_definitions_format_jsonを指定した場合_four_layerがparallel_axesを含みefficacy_axisを含まないこと():
    # Act
    r = _run("list-definitions", "--format", "json")
    payload = json.loads(r.stdout)  # array of definition summaries
    four_layer = next(d for d in payload if d["name"] == "four-layer-delegation-readiness")
    # Assert
    assert "parallel_axes" in four_layer
    assert "efficacy_axis" not in four_layer  # old singular key is gone
    axis_ids = {a["id"] for a in four_layer["parallel_axes"]}
    assert {"efficacy", "organization"} <= axis_ids
