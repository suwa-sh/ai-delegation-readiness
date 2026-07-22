"""Acceptance-gate tests for AI-generated patch ownership cost."""
from __future__ import annotations

import csv
import hashlib
import io
import json
import subprocess
from pathlib import Path

import pytest
import yaml

from adr import check_patch_ownership as po
from adr import io_input
from conftest import (
    REPO_ROOT,
    sample_patch_green_path,
    sample_patch_hollow_red_path,
    sample_patch_risk_yellow_path,
)

AIDR = REPO_ROOT / "bin" / "aidr"
RETROSPECTIVE_DIR = REPO_ROOT / "tests" / "fixtures" / "patch_ownership_validation"


def _run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(AIDR), *args], check=False, capture_output=True, text=True
    )


def _green_answers() -> dict:
    data, _, _ = io_input.load_input(sample_patch_green_path(), "patch-ownership")
    return dict(data["answers"])


def _write_yaml(tmp_path: Path, answers: dict, name: str = "patch.yaml") -> Path:
    path = tmp_path / name
    path.write_text(
        yaml.safe_dump({"patch": "test-patch", "answers": answers}, sort_keys=False),
        encoding="utf-8",
    )
    return path


@pytest.mark.parametrize(
    ("fixture", "exit_code", "region"),
    [
        (sample_patch_green_path, 0, "green"),
        (sample_patch_risk_yellow_path, 1, "yellow"),
        (sample_patch_hollow_red_path, 2, "red"),
    ],
)
def test_samples_cover_three_regions(fixture, exit_code, region):
    result = po.score(fixture())
    assert result.exit_code == exit_code
    assert result.region == region


@pytest.mark.parametrize("risk_id", [f"never_cheap.N{i}" for i in range(1, 6)])
def test_every_never_cheap_category_requires_human_decision(tmp_path, risk_id):
    answers = _green_answers()
    answers[risk_id] = "yes"
    answers["ownership.O4"] = "yes"
    answers["ownership.review_route_ref"] = (
        "file:review-route.md#sha256=" + "d" * 64
    )
    result = po.score(_write_yaml(tmp_path, answers))
    assert result.region == "yellow"
    assert result.risk_ids == [risk_id]


@pytest.mark.parametrize(
    ("anchor", "negative", "reviewed", "expected"),
    [
        (False, False, False, "red"),
        (False, False, True, "red"),
        (False, True, False, "red"),
        (False, True, True, "red"),
        (True, False, False, "red"),
        (True, False, True, "green"),
        (True, True, False, "green"),
        (True, True, True, "green"),
    ],
)
def test_hollow_green_is_anchor_and_one_independent_check(
    tmp_path, anchor, negative, reviewed, expected
):
    answers = _green_answers()
    answers["hollow_green.H1"] = anchor
    answers["hollow_green.H2"] = negative
    answers["hollow_green.H3"] = reviewed
    result = po.score(_write_yaml(tmp_path, answers))
    assert result.region == expected


def test_high_risk_without_review_route_is_red_not_input_error(tmp_path):
    answers = _green_answers()
    answers["never_cheap.N1"] = "yes"
    answers["ownership.O4"] = "yes"
    result = po.score(_write_yaml(tmp_path, answers))
    assert result.region == "red"
    assert "ownership.review_route_ref" in result.missing_controls


def test_absent_test_evidence_is_red(tmp_path):
    answers = _green_answers()
    answers["evidence.test_status"] = "absent"
    answers.pop("evidence.test_ref")
    result = po.score(_write_yaml(tmp_path, answers))
    assert result.region == "red"
    assert "evidence.test" in result.missing_controls


def test_not_applicable_test_requires_content_addressed_rationale(tmp_path):
    answers = _green_answers()
    answers["evidence.test_status"] = "not_applicable"
    answers.pop("evidence.test_ref")
    answers["evidence.test_na_ref"] = "file:test-na.md#sha256=" + "e" * 64
    assert po.score(_write_yaml(tmp_path, answers)).region == "green"


@pytest.mark.parametrize(
    "qid",
    ["evidence.patch_ref", "evidence.test_ref", "evidence.risk_manifest_ref"],
)
def test_placeholder_evidence_is_input_error(tmp_path, qid):
    answers = _green_answers()
    answers[qid] = "TBD"
    with pytest.raises(po.InputError, match="content-addressed"):
        po.score(_write_yaml(tmp_path, answers))


def test_unknown_yaml_id_is_input_error(tmp_path):
    answers = _green_answers()
    answers["probe.P99"] = "yes"
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))
    assert result.returncode == 3
    assert "unknown question id" in result.stderr


def test_non_string_yaml_id_is_input_error_without_traceback(tmp_path):
    answers = _green_answers()
    answers[7] = "yes"
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))
    assert result.returncode == 3
    assert "must be strings" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "yaml_text",
    [
        "7: ignored\npatch: x\nanswers: {}\n",
        "? [probe.P1]\n: yes\npatch: x\nanswers: {}\n",
    ],
)
def test_all_yaml_mapping_keys_must_be_strings(tmp_path, yaml_text):
    path = tmp_path / "bad-key.yaml"
    path.write_text(yaml_text, encoding="utf-8")
    result = _run("check-patch-ownership", str(path))
    assert result.returncode == 3
    assert "mapping keys must be strings" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize("patch_value", [{"name": "boom"}, [], 7, ""])
def test_patch_metadata_must_be_non_empty_string(tmp_path, patch_value):
    path = tmp_path / "bad-patch.yaml"
    path.write_text(
        yaml.safe_dump({"patch": patch_value, "answers": _green_answers()}),
        encoding="utf-8",
    )
    for output_format in ("text", "json", "csv"):
        result = _run(
            "check-patch-ownership", str(path), "--format", output_format
        )
        assert result.returncode == 3
        assert "'patch' must be a non-empty string" in result.stderr
        assert "Traceback" not in result.stderr


def test_duplicate_yaml_key_is_input_error_without_traceback(tmp_path):
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "patch: x\nanswers:\n  probe.P1: yes\n  probe.P1: no\n",
        encoding="utf-8",
    )
    result = _run("check-patch-ownership", str(path))
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


def test_duplicate_overlay_key_is_input_error_without_traceback(tmp_path):
    overlay = tmp_path / "duplicate-overlay.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\nextends: other\n",
        encoding="utf-8",
    )
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr
    overlay_check = _run("check-overlay", str(overlay))
    initialized = _run(
        "init", "--target", "patch-ownership", "--overlay", str(overlay)
    )
    listed = _run(
        "list-definitions", "--target", "patch-ownership", "--overlay", str(overlay)
    )
    for command_result in (overlay_check, initialized, listed):
        assert command_result.returncode == 3
        assert "duplicate key" in command_result.stderr
        assert "Traceback" not in command_result.stderr


@pytest.mark.parametrize(
    "ref",
    [
        "file:/etc/passwd#sha256=" + "a" * 64,
        "file:../secret.txt#sha256=" + "a" * 64,
        "file:proof/../../secret.txt#sha256=" + "a" * 64,
    ],
)
def test_file_evidence_must_be_relative_without_traversal(tmp_path, ref):
    answers = _green_answers()
    answers["evidence.risk_manifest_ref"] = ref
    with pytest.raises(po.InputError, match="relative path"):
        po.score(_write_yaml(tmp_path, answers))


def test_successful_json_has_schema_version(tmp_path):
    result = _run(
        "check-patch-ownership", str(sample_patch_green_path()), "--format", "json"
    )
    payload = json.loads(result.stdout)
    assert result.returncode == 0
    assert payload["schema_version"] == "1"
    assert payload["region"] == "green"


def test_successful_csv_has_fixed_header():
    result = subprocess.run(
        [str(AIDR), "check-patch-ownership", str(sample_patch_green_path()), "--format", "csv"],
        check=False,
        capture_output=True,
    )
    rows = list(csv.reader(io.StringIO(result.stdout.decode("utf-8-sig"))))
    assert result.returncode == 0
    assert rows[0] == [
        "schema_version", "record_type", "patch", "id", "name", "level",
        "score", "threshold", "details", "notes",
    ]


def test_overlay_added_probe_question_is_required_for_green(tmp_path):
    overlay = tmp_path / "overlay.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: probe.LOCAL1\n"
        "    kind: question\n"
        "    text: Is the local rollback drill recorded?\n"
        "    text_ja: ローカルのロールバック訓練を記録したか\n",
        encoding="utf-8",
    )
    answers = _green_answers()
    answers["probe.LOCAL1"] = "no"
    result = po.score(_write_yaml(tmp_path, answers), overlay_paths=[overlay])
    assert result.region == "yellow"
    assert "probe.LOCAL1" in result.missing_controls


def test_strengthened_ownership_threshold_changes_gate_and_display(tmp_path):
    overlay = tmp_path / "stronger.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  ownership: {threshold: 4}\n",
        encoding="utf-8",
    )
    result = po.score(sample_patch_green_path(), overlay_paths=[overlay])
    ownership = next(group for group in result.groups if group.id == "ownership")
    assert result.region == "yellow"
    assert ownership.level == "partial"
    assert ownership.score == 3
    assert ownership.threshold == 4
    assert "ownership.O4" in result.missing_controls


def test_impossible_strengthened_threshold_is_input_error(tmp_path):
    overlay = tmp_path / "impossible.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  probe: {threshold: 999}\n",
        encoding="utf-8",
    )
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )
    assert result.returncode == 3
    assert "between 1 and 5" in result.stderr


def test_fractional_strengthened_threshold_is_rejected(tmp_path):
    overlay = tmp_path / "fractional.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  ownership: {threshold: 3.5}\n",
        encoding="utf-8",
    )
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )
    assert result.returncode == 3
    assert "must be an integer" in result.stderr


@pytest.mark.parametrize("owner", ["user:<id>", "team:TBD", "user:x"])
def test_owner_placeholders_cannot_open_green_gate(tmp_path, owner):
    answers = _green_answers()
    answers["ownership.owner_ref"] = owner
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))
    assert result.returncode == 3
    assert "ownership.owner_ref" in result.stderr


def test_normal_ownership_display_cannot_mask_required_control(tmp_path):
    answers = _green_answers()
    answers["ownership.O3"] = "no"
    answers["ownership.O4"] = "yes"
    result = po.score(_write_yaml(tmp_path, answers))
    ownership = next(group for group in result.groups if group.id == "ownership")
    assert result.region == "yellow"
    assert ownership.level == "partial"
    assert ownership.score == 2
    assert ownership.threshold == 3
    assert ownership.no_ids == ["ownership.O3"]


def test_patch_overlay_contract_is_consistent_across_commands(tmp_path):
    overlay = tmp_path / "bad-kind.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: probe.BAD\n    kind: data\n    label: bad\n    label_ja: 不正\n",
        encoding="utf-8",
    )
    checked = _run("check-overlay", str(overlay))
    initialized = _run(
        "init", "--target", "patch-ownership", "--overlay", str(overlay)
    )
    listed = _run(
        "list-definitions", "--target", "patch-ownership", "--overlay", str(overlay)
    )
    assert checked.returncode == 1
    assert initialized.returncode == 3
    assert listed.returncode == 3


@pytest.mark.parametrize(
    "overlay_text",
    [
        "[]\n",
        "version: 1\nextends: patch-ownership\nadd:\n  - id: 7\n",
        "version: 1\nextends: patch-ownership\nadd: {}\n",
        "version: 1\nextends: patch-ownership\nstrengthen: []\n",
    ],
)
def test_malformed_overlay_shape_is_input_error_without_traceback(
    tmp_path, overlay_text
):
    overlay = tmp_path / "bad-shape.yaml"
    overlay.write_text(overlay_text, encoding="utf-8")
    results = [
        _run(
            "check-patch-ownership",
            str(sample_patch_green_path()),
            "--overlay",
            str(overlay),
        ),
        _run("check-overlay", str(overlay)),
    ]
    for result in results:
        assert result.returncode == 3
        assert "[ERROR]" in result.stderr
        assert "Traceback" not in result.stderr


def test_overlay_cannot_extend_hollow_green(tmp_path):
    overlay = tmp_path / "hollow-overlay.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: hollow_green.LOCAL1\n"
        "    kind: question\n"
        "    text: Extra hollow check?\n"
        "    text_ja: hollow green の追加検査か\n",
        encoding="utf-8",
    )
    result = _run("check-overlay", str(overlay))
    assert result.returncode == 1
    assert "not an add-able extension point" in result.stdout


@pytest.mark.parametrize("path", sorted(RETROSPECTIVE_DIR.glob("*.yaml")))
def test_redacted_real_patch_retrospectives_match_expected_region(path):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    result = po.score(path)
    assert data["retrospective"]["raw_diff_stored"] is False
    assert result.region == data["retrospective"]["expected_region"]
    assert len(data["retrospective"]["commit"]) == 40
    assert len(data["retrospective"]["diff_sha256"]) == 64
    manifest_ref = data["answers"]["evidence.risk_manifest_ref"]
    manifest_path, declared_digest = manifest_ref.removeprefix("file:").split(
        "#sha256=", 1
    )
    manifest_bytes = (REPO_ROOT / manifest_path).read_bytes()
    assert hashlib.sha256(manifest_bytes).hexdigest() == declared_digest
