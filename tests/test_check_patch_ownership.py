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


def _write_overlay(tmp_path: Path, name: str, content: str) -> Path:
    path = tmp_path / name
    path.write_text(content, encoding="utf-8")
    return path


@pytest.mark.parametrize(
    ("fixture", "exit_code", "region"),
    [
        pytest.param(
            sample_patch_green_path,
            0,
            "green",
            id="所有可能sampleの場合_greenかつexit0になること",
        ),
        pytest.param(
            sample_patch_risk_yellow_path,
            1,
            "yellow",
            id="高risk_sampleの場合_yellowかつexit1になること",
        ),
        pytest.param(
            sample_patch_hollow_red_path,
            2,
            "red",
            id="hollow_green_sampleの場合_redかつexit2になること",
        ),
    ],
)
def test_score_3領域のsampleを採点した場合_期待regionとexit_codeになること(
    fixture, exit_code, region
):
    # Act
    result = po.score(fixture())

    # Assert
    assert result.exit_code == exit_code
    assert result.region == region


@pytest.mark.parametrize(
    "risk_id",
    [
        pytest.param(
            f"never_cheap.N{i}",
            id=f"N{i}がyesの場合_yellowになること",
        )
        for i in range(1, 6)
    ],
)
def test_score_never_cheapの各categoryがyesの場合_人間判断のyellowになること(
    tmp_path, risk_id
):
    # Arrange
    answers = _green_answers()
    answers[risk_id] = "yes"
    answers["ownership.O4"] = "yes"
    answers["ownership.review_route_ref"] = (
        "file:review-route.md#sha256=" + "d" * 64
    )

    # Act
    result = po.score(_write_yaml(tmp_path, answers))

    # Assert
    assert result.region == "yellow"
    assert result.risk_ids == [risk_id]


@pytest.mark.parametrize(
    ("anchor", "negative", "reviewed", "expected"),
    [
        pytest.param(
            False, False, False, "red",
            id="anchorなしnegativeなしreviewなしの場合_redになること",
        ),
        pytest.param(
            False, False, True, "red",
            id="anchorなしnegativeなしreviewありの場合_redになること",
        ),
        pytest.param(
            False, True, False, "red",
            id="anchorなしnegativeありreviewなしの場合_redになること",
        ),
        pytest.param(
            False, True, True, "red",
            id="anchorなしnegativeありreviewありの場合_redになること",
        ),
        pytest.param(
            True, False, False, "red",
            id="anchorありnegativeなしreviewなしの場合_redになること",
        ),
        pytest.param(
            True, False, True, "green",
            id="anchorありnegativeなしreviewありの場合_greenになること",
        ),
        pytest.param(
            True, True, False, "green",
            id="anchorありnegativeありreviewなしの場合_greenになること",
        ),
        pytest.param(
            True, True, True, "green",
            id="anchorありnegativeありreviewありの場合_greenになること",
        ),
    ],
)
def test_score_hollow_green条件を組み合わせた場合_anchorかつ独立checkで判定すること(
    tmp_path, anchor, negative, reviewed, expected
):
    # Arrange
    answers = _green_answers()
    answers["hollow_green.H1"] = anchor
    answers["hollow_green.H2"] = negative
    answers["hollow_green.H3"] = reviewed

    # Act
    result = po.score(_write_yaml(tmp_path, answers))

    # Assert
    assert result.region == expected


def test_score_高riskでreview_routeがない場合_input_errorでなくredになること(tmp_path):
    # Arrange
    answers = _green_answers()
    answers["never_cheap.N1"] = "yes"
    answers["ownership.O4"] = "yes"

    # Act
    result = po.score(_write_yaml(tmp_path, answers))

    # Assert
    assert result.region == "red"
    assert "ownership.review_route_ref" in result.missing_controls


def test_score_test_evidenceがabsentの場合_redになること(tmp_path):
    # Arrange
    answers = _green_answers()
    answers["evidence.test_status"] = "absent"
    answers.pop("evidence.test_ref")

    # Act
    result = po.score(_write_yaml(tmp_path, answers))

    # Assert
    assert result.region == "red"
    assert "evidence.test" in result.missing_controls


def test_score_testがnot_applicableで根拠refがある場合_greenになること(tmp_path):
    # Arrange
    answers = _green_answers()
    answers["evidence.test_status"] = "not_applicable"
    answers.pop("evidence.test_ref")
    answers["evidence.test_na_ref"] = "file:test-na.md#sha256=" + "e" * 64

    # Act
    result = po.score(_write_yaml(tmp_path, answers))

    # Assert
    assert result.region == "green"


@pytest.mark.parametrize(
    "qid",
    [
        pytest.param(
            "evidence.patch_ref",
            id="patch_refがTBDの場合_InputErrorになること",
        ),
        pytest.param(
            "evidence.test_ref",
            id="test_refがTBDの場合_InputErrorになること",
        ),
        pytest.param(
            "evidence.risk_manifest_ref",
            id="risk_manifest_refがTBDの場合_InputErrorになること",
        ),
    ],
)
def test_score_証拠refがplaceholderの場合_InputErrorになること(tmp_path, qid):
    # Arrange
    answers = _green_answers()
    answers[qid] = "TBD"

    # Act & Assert
    with pytest.raises(po.InputError, match="content-addressed"):
        po.score(_write_yaml(tmp_path, answers))


def test_aidr_check_patch_ownership_YAMLに未知idがある場合_exit3で理由を返すこと(
    tmp_path,
):
    # Arrange
    answers = _green_answers()
    answers["probe.P99"] = "yes"

    # Act
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))

    # Assert
    assert result.returncode == 3
    assert "unknown question id" in result.stderr


def test_aidr_check_patch_ownership_YAMLのidが文字列でない場合_tracebackなしでexit3になること(
    tmp_path,
):
    # Arrange
    answers = _green_answers()
    answers[7] = "yes"

    # Act
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))

    # Assert
    assert result.returncode == 3
    assert "must be strings" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "yaml_text",
    [
        pytest.param(
            "7: ignored\npatch: x\nanswers: {}\n",
            id="top_level_keyが数値の場合_exit3になること",
        ),
        pytest.param(
            "? [probe.P1]\n: yes\npatch: x\nanswers: {}\n",
            id="top_level_keyがlistの場合_exit3になること",
        ),
    ],
)
def test_aidr_check_patch_ownership_YAMLのmapping_keyが文字列でない場合_exit3になること(
    tmp_path, yaml_text
):
    # Arrange
    path = tmp_path / "bad-key.yaml"
    path.write_text(yaml_text, encoding="utf-8")

    # Act
    result = _run("check-patch-ownership", str(path))

    # Assert
    assert result.returncode == 3
    assert "mapping keys must be strings" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "patch_value",
    [
        pytest.param({"name": "boom"}, id="patchがmappingの場合_exit3になること"),
        pytest.param([], id="patchがlistの場合_exit3になること"),
        pytest.param(7, id="patchが数値の場合_exit3になること"),
        pytest.param("", id="patchが空文字の場合_exit3になること"),
    ],
)
def test_aidr_check_patch_ownership_patchが空でない文字列でない場合_全formatでexit3になること(
    tmp_path, patch_value
):
    # Arrange
    path = tmp_path / "bad-patch.yaml"
    path.write_text(
        yaml.safe_dump({"patch": patch_value, "answers": _green_answers()}),
        encoding="utf-8",
    )

    # Act
    results = [
        _run(
            "check-patch-ownership", str(path), "--format", output_format
        )
        for output_format in ("text", "json", "csv")
    ]

    # Assert
    for result in results:
        assert result.returncode == 3
        assert "'patch' must be a non-empty string" in result.stderr
        assert "Traceback" not in result.stderr


def test_aidr_check_patch_ownership_YAMLに重複keyがある場合_tracebackなしでexit3になること(
    tmp_path,
):
    # Arrange
    path = tmp_path / "duplicate.yaml"
    path.write_text(
        "patch: x\nanswers:\n  probe.P1: yes\n  probe.P1: no\n",
        encoding="utf-8",
    )

    # Act
    result = _run("check-patch-ownership", str(path))

    # Assert
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


def test_aidr_check_patch_ownership_overlayに重複keyがある場合_tracebackなしでexit3になること(
    tmp_path,
):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "duplicate-overlay.yaml",
        "version: 1\nextends: patch-ownership\nextends: other\n",
    )

    # Act
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )

    # Assert
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


def test_aidr_check_overlay_overlayに重複keyがある場合_tracebackなしでexit3になること(
    tmp_path,
):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "duplicate-overlay.yaml",
        "version: 1\nextends: patch-ownership\nextends: other\n",
    )

    # Act
    result = _run("check-overlay", str(overlay))

    # Assert
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


def test_aidr_init_overlayに重複keyがある場合_tracebackなしでexit3になること(tmp_path):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "duplicate-overlay.yaml",
        "version: 1\nextends: patch-ownership\nextends: other\n",
    )

    # Act
    result = _run("init", "--target", "patch-ownership", "--overlay", str(overlay))

    # Assert
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


def test_aidr_list_definitions_overlayに重複keyがある場合_tracebackなしでexit3になること(
    tmp_path,
):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "duplicate-overlay.yaml",
        "version: 1\nextends: patch-ownership\nextends: other\n",
    )

    # Act
    result = _run(
        "list-definitions",
        "--target",
        "patch-ownership",
        "--overlay",
        str(overlay),
    )

    # Assert
    assert result.returncode == 3
    assert "duplicate key" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "ref",
    [
        pytest.param(
            "file:/etc/passwd#sha256=" + "a" * 64,
            id="絶対pathの場合_InputErrorになること",
        ),
        pytest.param(
            "file:../secret.txt#sha256=" + "a" * 64,
            id="親directory参照の場合_InputErrorになること",
        ),
        pytest.param(
            "file:proof/../../secret.txt#sha256=" + "a" * 64,
            id="途中にtraversalがある場合_InputErrorになること",
        ),
    ],
)
def test_score_file証拠refが相対pathでない場合_InputErrorになること(tmp_path, ref):
    # Arrange
    answers = _green_answers()
    answers["evidence.risk_manifest_ref"] = ref

    # Act & Assert
    with pytest.raises(po.InputError, match="relative path"):
        po.score(_write_yaml(tmp_path, answers))


def test_aidr_check_patch_ownership_JSON出力が成功した場合_schema_versionを含むこと():
    # Act
    result = _run(
        "check-patch-ownership", str(sample_patch_green_path()), "--format", "json"
    )
    payload = json.loads(result.stdout)

    # Assert
    assert result.returncode == 0
    assert payload["schema_version"] == "1"
    assert payload["region"] == "green"


def test_aidr_check_patch_ownership_CSV出力が成功した場合_固定headerになること():
    # Act
    result = subprocess.run(
        [str(AIDR), "check-patch-ownership", str(sample_patch_green_path()), "--format", "csv"],
        check=False,
        capture_output=True,
    )
    rows = list(csv.reader(io.StringIO(result.stdout.decode("utf-8-sig"))))

    # Assert
    assert result.returncode == 0
    assert rows[0] == [
        "schema_version", "record_type", "patch", "id", "name", "level",
        "score", "threshold", "details", "notes",
    ]


def test_score_overlayでprobe質問を追加した場合_greenの必須条件になること(tmp_path):
    # Arrange
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

    # Act
    result = po.score(_write_yaml(tmp_path, answers), overlay_paths=[overlay])

    # Assert
    assert result.region == "yellow"
    assert "probe.LOCAL1" in result.missing_controls


def test_score_overlayでownership閾値を強化した場合_gateと表示に反映されること(tmp_path):
    # Arrange
    overlay = tmp_path / "stronger.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  ownership: {threshold: 4}\n",
        encoding="utf-8",
    )

    # Act
    result = po.score(sample_patch_green_path(), overlay_paths=[overlay])
    ownership = next(group for group in result.groups if group.id == "ownership")

    # Assert
    assert result.region == "yellow"
    assert ownership.level == "partial"
    assert ownership.score == 3
    assert ownership.threshold == 4
    assert "ownership.O4" in result.missing_controls


def test_aidr_check_patch_ownership_overlay閾値が質問数を超える場合_exit3になること(
    tmp_path,
):
    # Arrange
    overlay = tmp_path / "impossible.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  probe: {threshold: 999}\n",
        encoding="utf-8",
    )

    # Act
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )

    # Assert
    assert result.returncode == 3
    assert "between 1 and 5" in result.stderr


def test_aidr_check_patch_ownership_overlay閾値が小数の場合_exit3になること(tmp_path):
    # Arrange
    overlay = tmp_path / "fractional.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\n"
        "strengthen:\n  ownership: {threshold: 3.5}\n",
        encoding="utf-8",
    )

    # Act
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )

    # Assert
    assert result.returncode == 3
    assert "must be an integer" in result.stderr


@pytest.mark.parametrize(
    "owner",
    [
        pytest.param("user:<id>", id="placeholder_idの場合_exit3になること"),
        pytest.param("team:TBD", id="TBDの場合_exit3になること"),
        pytest.param("user:x", id="短すぎるidの場合_exit3になること"),
    ],
)
def test_aidr_check_patch_ownership_owner_refがplaceholderの場合_exit3になること(
    tmp_path, owner
):
    # Arrange
    answers = _green_answers()
    answers["ownership.owner_ref"] = owner

    # Act
    result = _run("check-patch-ownership", str(_write_yaml(tmp_path, answers)))

    # Assert
    assert result.returncode == 3
    assert "ownership.owner_ref" in result.stderr


def test_score_ownership得点が閾値未満の場合_O4で不足を隠せないこと(tmp_path):
    # Arrange
    answers = _green_answers()
    answers["ownership.O3"] = "no"
    answers["ownership.O4"] = "yes"

    # Act
    result = po.score(_write_yaml(tmp_path, answers))
    ownership = next(group for group in result.groups if group.id == "ownership")

    # Assert
    assert result.region == "yellow"
    assert ownership.level == "partial"
    assert ownership.score == 2
    assert ownership.threshold == 3
    assert ownership.no_ids == ["ownership.O3"]


def test_aidr_check_overlay_patch_overlayのkindが不正な場合_exit1で拒否すること(tmp_path):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "bad-kind.yaml",
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: probe.BAD\n    kind: data\n    label: bad\n    label_ja: 不正\n",
    )

    # Act
    result = _run("check-overlay", str(overlay))

    # Assert
    assert result.returncode == 1


def test_aidr_init_patch_overlayのkindが不正な場合_exit3で拒否すること(tmp_path):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "bad-kind.yaml",
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: probe.BAD\n    kind: data\n    label: bad\n    label_ja: 不正\n",
    )

    # Act
    result = _run("init", "--target", "patch-ownership", "--overlay", str(overlay))

    # Assert
    assert result.returncode == 3


def test_aidr_list_definitions_patch_overlayのkindが不正な場合_exit3で拒否すること(
    tmp_path,
):
    # Arrange
    overlay = _write_overlay(
        tmp_path,
        "bad-kind.yaml",
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: probe.BAD\n    kind: data\n    label: bad\n    label_ja: 不正\n",
    )

    # Act
    result = _run(
        "list-definitions", "--target", "patch-ownership", "--overlay", str(overlay)
    )

    # Assert
    assert result.returncode == 3


@pytest.mark.parametrize(
    "overlay_text",
    [
        pytest.param("[]\n", id="rootがlistの場合_exit3になること"),
        pytest.param(
            "version: 1\nextends: patch-ownership\nadd:\n  - id: 7\n",
            id="追加idが数値の場合_exit3になること",
        ),
        pytest.param(
            "version: 1\nextends: patch-ownership\nadd: {}\n",
            id="addがmappingの場合_exit3になること",
        ),
        pytest.param(
            "version: 1\nextends: patch-ownership\nstrengthen: []\n",
            id="strengthenがlistの場合_exit3になること",
        ),
    ],
)
def test_aidr_check_patch_ownership_overlayの構造が不正な場合_tracebackなしでexit3になること(
    tmp_path, overlay_text
):
    # Arrange
    overlay = _write_overlay(tmp_path, "bad-shape.yaml", overlay_text)

    # Act
    result = _run(
        "check-patch-ownership",
        str(sample_patch_green_path()),
        "--overlay",
        str(overlay),
    )

    # Assert
    assert result.returncode == 3
    assert "[ERROR]" in result.stderr
    assert "Traceback" not in result.stderr


@pytest.mark.parametrize(
    "overlay_text",
    [
        pytest.param("[]\n", id="rootがlistの場合_exit3になること"),
        pytest.param(
            "version: 1\nextends: patch-ownership\nadd:\n  - id: 7\n",
            id="追加idが数値の場合_exit3になること",
        ),
        pytest.param(
            "version: 1\nextends: patch-ownership\nadd: {}\n",
            id="addがmappingの場合_exit3になること",
        ),
        pytest.param(
            "version: 1\nextends: patch-ownership\nstrengthen: []\n",
            id="strengthenがlistの場合_exit3になること",
        ),
    ],
)
def test_aidr_check_overlay_overlayの構造が不正な場合_tracebackなしでexit3になること(
    tmp_path, overlay_text
):
    # Arrange
    overlay = _write_overlay(tmp_path, "bad-shape.yaml", overlay_text)

    # Act
    result = _run("check-overlay", str(overlay))

    # Assert
    assert result.returncode == 3
    assert "[ERROR]" in result.stderr
    assert "Traceback" not in result.stderr


def test_aidr_check_overlay_hollow_greenへ質問を追加した場合_拒否すること(tmp_path):
    # Arrange
    overlay = tmp_path / "hollow-overlay.yaml"
    overlay.write_text(
        "version: 1\nextends: patch-ownership\nadd:\n"
        "  - id: hollow_green.LOCAL1\n"
        "    kind: question\n"
        "    text: Extra hollow check?\n"
        "    text_ja: hollow green の追加検査か\n",
        encoding="utf-8",
    )

    # Act
    result = _run("check-overlay", str(overlay))

    # Assert
    assert result.returncode == 1
    assert "not an add-able extension point" in result.stdout


@pytest.mark.parametrize(
    "path",
    sorted(RETROSPECTIVE_DIR.glob("*.yaml")),
    ids=lambda path: f"{path.stem}の場合_期待regionとdigestに一致すること",
)
def test_score_redacted回顧fixtureを採点した場合_期待regionとdigestに一致すること(path):
    # Arrange
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    manifest_ref = data["answers"]["evidence.risk_manifest_ref"]
    manifest_path, declared_digest = manifest_ref.removeprefix("file:").split(
        "#sha256=", 1
    )
    manifest_bytes = (REPO_ROOT / manifest_path).read_bytes()

    # Act
    result = po.score(path)
    actual_digest = hashlib.sha256(manifest_bytes).hexdigest()

    # Assert
    assert data["retrospective"]["raw_diff_stored"] is False
    assert result.region == data["retrospective"]["expected_region"]
    assert len(data["retrospective"]["commit"]) == 40
    assert len(data["retrospective"]["diff_sha256"]) == 64
    assert actual_digest == declared_digest
