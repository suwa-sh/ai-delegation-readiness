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

from adr import check_patch_ownership as po
from conftest import (
    REPO_ROOT,
    patch_decision_team_bands_overlay_path,
    sample_audit_log_path,
    sample_business_path,
    sample_judgments_path,
    sample_overlay_path,
    sample_patch_decisions_demo_path,
    sample_patch_decisions_midori_path,
    sample_task_contract_green_path,
    sample_task_contract_red_path,
)

AIDR = REPO_ROOT / "bin" / "aidr"


def _decision_gate(region: str = "green", **overrides) -> dict:
    """A schema-valid gate block, block_sha256 included.

    summarize-patch-decisions recomputes block_sha256 on every load and
    rejects a mismatch, so a hand-typed placeholder value would make any
    synthetic record fail before the behavior under test is reached.
    """
    gate = {
        "region": region,
        "risk_ids": [],
        "missing_controls": [],
        "gate_json_sha256": "a" * 64,
        "definition_name": "patch-ownership",
        "definition_version": 1,
        "overlays": [],
    }
    gate.update(overrides)
    gate["block_sha256"] = po.gate_block_digest(gate)
    return gate


def _decision_record(
    patch_id: str,
    decision: str,
    team: str = "t",
    recorded_at: str = "2026-07-01T00:00:00Z",
    decided_on: str | None = "2026-07-01",
    discard_reason: str | None = None,
    gate: dict | None = None,
) -> dict:
    record = {
        "schema_version": "1",
        "patch_id": patch_id,
        "team": team,
        "recorded_at": recorded_at,
        "decision": decision,
        "gate": gate or _decision_gate(),
    }
    if decided_on is not None:
        record["decided_on"] = decided_on
    if discard_reason is not None:
        record["discard_reason"] = discard_reason
    return record


def _write_decision_records(path: Path, records: list[dict]) -> Path:
    path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n",
        encoding="utf-8",
    )
    return path


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
    ["screen-transition", "check-readiness", "score-delegation", "check-task-contract", "check-patch-ownership", "summarize-patch-decisions", "validate-audit-log", "check-overlay", "list-definitions"],
    ids=[
        "screen_transitionの場合_exit0でusageを含むこと",
        "check_readinessの場合_exit0でusageを含むこと",
        "score_delegationの場合_exit0でusageを含むこと",
        "check_task_contractの場合_exit0でusageを含むこと",
        "check_patch_ownershipの場合_exit0でusageを含むこと",
        "summarize_patch_decisionsの場合_exit0でusageを含むこと",
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


# --- summarize-patch-decisions ------------------------------------------------

def test_aidr_summarize_patch_decisions_redを含むmidoriサンプルの場合_exit2になること():
    """The sample has a RED-accepted patch, so the contradiction check fires."""
    # Act
    r = _run("summarize-patch-decisions", str(sample_patch_decisions_midori_path()))
    # Assert
    assert r.returncode == 2
    assert "[NG] RED accepted: 1" in r.stdout


def test_aidr_summarize_patch_decisions_存在しないpathを渡した場合_exit3になること():
    # Act
    r = _run("summarize-patch-decisions", "/tmp/does-not-exist-patch-decisions.jsonl")
    # Assert
    assert r.returncode == 3
    assert "[ERROR]" in r.stderr
    assert "Traceback" not in r.stderr


def test_aidr_summarize_patch_decisions_未宣言のdiscard_reasonを含む場合_exit3になること(
    tmp_path,
):
    # Arrange
    record = _decision_record(
        "p1", "discarded", gate=_decision_gate("red"), discard_reason="not_declared",
    )
    bad = _write_decision_records(tmp_path / "bad.jsonl", [record])
    # Act
    r = _run("summarize-patch-decisions", str(bad))
    # Assert
    assert r.returncode == 3
    assert "unknown discard_reason" in r.stderr


def test_aidr_summarize_patch_decisions_format_jsonを指定した場合_discard_rateとexit_codeを含むこと():
    # Act
    r = _run(
        "summarize-patch-decisions", str(sample_patch_decisions_midori_path()),
        "--format", "json",
    )
    payload = json.loads(r.stdout)
    # Assert
    assert r.returncode == 2
    assert payload["schema_version"] == "1"
    assert payload["discard_rate"] == pytest.approx(0.25)
    assert payload["decided_rate"] == pytest.approx(12 / 13)
    assert payload["exit_code"] == 2


def test_aidr_summarize_patch_decisions_demo_from_fixturesの場合_discard_rateが0であること():
    # Act
    r = _run(
        "summarize-patch-decisions", str(sample_patch_decisions_demo_path()),
        "--format", "json",
    )
    payload = json.loads(r.stdout)
    # Assert
    assert r.returncode == 2  # red-accepted patches, even though nothing was discarded
    assert payload["discard_rate"] == 0.0
    assert payload["discarded"] == 0


def test_aidr_summarize_patch_decisions_teamとperiodで絞り込んだ場合_0件でもexit0になること():
    # Act
    r = _run(
        "summarize-patch-decisions", str(sample_patch_decisions_midori_path()),
        "--team", "no-such-team", "--period", "2099-01",
    )
    # Assert
    assert r.returncode == 0
    assert "No records matched" in r.stdout


@pytest.mark.parametrize(
    "period",
    [
        pytest.param("2026-7", id="月が1桁の場合_exit3になること"),
        pytest.param("2026-13", id="月が13の場合_exit3になること"),
        pytest.param("garbage", id="数字形式でない場合_exit3になること"),
    ],
)
def test_aidr_summarize_patch_decisions_periodの形式が不正な場合_exit3になること(period):
    # Act
    r = _run(
        "summarize-patch-decisions", str(sample_patch_decisions_midori_path()),
        "--period", period,
    )
    # Assert
    assert r.returncode == 3
    assert "--period must be" in r.stderr


def test_aidr_summarize_patch_decisions_overlayで理由を追加した場合_exit0になること(
    tmp_path,
):
    # Arrange
    record = _decision_record("p1", "discarded", discard_reason="vendor_contract_conflict")
    path = _write_decision_records(tmp_path / "overlay-reason.jsonl", [record])
    # Act
    r = _run(
        "summarize-patch-decisions", str(path),
        "--overlay", str(patch_decision_team_bands_overlay_path()),
    )
    # Assert
    assert r.returncode == 0
    assert "vendor_contract_conflict" in r.stdout


# --- list-definitions --target patch-decision ---------------------------------

def test_aidr_list_definitions_patch_decisionターゲットの場合_discard_reasonとbandsを含むこと():
    # Act
    r = _run("list-definitions", "--target", "patch-decision")
    # Assert
    assert r.returncode == 0
    assert "discard_reason" in r.stdout
    assert "bands" in r.stdout


def test_aidr_list_definitions_patch_decisionにoverlayを渡した場合_追加idを表示すること():
    # Act
    r = _run(
        "list-definitions", "--target", "patch-decision",
        "--overlay", str(patch_decision_team_bands_overlay_path()),
    )
    # Assert
    assert r.returncode == 0
    assert "+added: discard_reason.vendor_contract_conflict" in r.stdout
    assert "bands.healthy" in r.stdout
