"""aidr init (answer-file template generator) tests."""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

import overlay_scoring as ov
from adr import init_input as ii
from conftest import (
    EXAMPLES_DIR,
    four_layer_path,
    hs_overlay_four_layer_path,
    insourcing_overlay_path,
    matrix_path,
    patch_ownership_path,
    sample_overlay_path,
    task_contract_path,
    transition_path,
)

_DEF_PATHS = {
    "four-layer": four_layer_path,
    "matrix": matrix_path,
    "transition": transition_path,
    "task-contract": task_contract_path,
    "patch-ownership": patch_ownership_path,
}


def _question_ids(defn_path: Path, exclude_groups: set[str]) -> set[str]:
    defn = ov.load_yaml(defn_path)
    groups = ov.group_items(defn)
    return {
        leaf["id"]
        for gid, g in groups.items()
        if gid not in exclude_groups
        for leaf in g["leaves"]
        if leaf.get("kind", "question") == "question"
    }


@pytest.mark.parametrize(
    "target",
    sorted(ii.TARGETS),
    ids=[f"{t}を指定した場合_有効なyamlで全質問を網羅すること" for t in sorted(ii.TARGETS)],
)
def test_generate_targetを指定した場合_有効なyamlで全質問を網羅すること(target):
    # Act
    text = ii.generate(target)
    data = yaml.safe_load(text)

    # Assert
    assert isinstance(data, dict)
    filename, exclude = ii.TARGETS[target]
    expected = _question_ids(_DEF_PATHS[target](), exclude)
    # 質問 id はテンプレート本文に必ず現れる(値は空 = 未回答)
    for qid in expected:
        assert f"{qid}:" in text, f"{target}: template misses {qid}"
    # 問いコメントは text_ja 由来
    assert "# 問: " in text


def test_generate_overlayを渡した場合_追加質問と問いコメントが出力に含まれること():
    # Act
    text = ii.generate("four-layer", overlay_paths=[sample_overlay_path()])

    # Assert
    assert "L1.MIDORI_Q5:" in text and "L4.MIDORI_Q6:" in text
    assert "法務のレビュー" in text  # overlay の text_ja がコメントに出る
    # overlay 付き出力も valid YAML であること
    assert isinstance(yaml.safe_load(text), dict)


def test_generate_task_contractの場合_dataリーフのキーを含むこと():
    """これが欠けたテンプレートは check-task-contract で exit 3 になる。"""
    # Act
    text = ii.generate("task-contract")

    # Assert
    assert "scorer.type:" in text
    assert "scorer.iruler_double_eval:" in text


def test_generate_複数行text_jaのoverlayを渡した場合_有効なyamlを生成すること(tmp_path):
    # Arrange
    ov_path = tmp_path / "multiline.yaml"
    ov_path.write_text(
        "version: 1\n"
        "extends: four-layer-delegation-readiness\n"
        "add:\n"
        '  - id: "L1.ML_Q9"\n'
        "    text: multi-line question\n"
        "    text_ja: |\n"
        "      一行目\n"
        "      二行目: 詳細\n"
        "    weight: 1.0\n"
    )

    # Act
    text = ii.generate("four-layer", overlay_paths=[ov_path])

    # Assert
    data = yaml.safe_load(text)  # ParserError にならないこと
    assert isinstance(data, dict)
    assert "一行目 二行目: 詳細" in text  # 1 行に正規化される


def test_generate_ゲート層overlayを渡した場合_ゲート層が並列軸より前に出力されること():
    # Act
    text = ii.generate("four-layer", overlay_paths=[hs_overlay_four_layer_path()])

    # Assert
    pos_l5 = text.index("L5.Q1:")
    pos_eff = text.index("efficacy.E1:")
    pos_org = text.index("organization.C1:")
    assert pos_l5 < pos_eff < pos_org


def test_generate_未知のtargetを指定した場合_ValueErrorが送出されること():
    # Act & Assert
    with pytest.raises(ValueError):
        ii.generate("nope")


# --- 同梱 examples の「問:」コメントが定義の text_ja とドリフトしていないこと ---

_QUESTION_COMMENT_RE = re.compile(r"^\s*([\w.]+):[^#\n]*#\s*問:\s*(.+?)(?:\s*→.*)?$")


def _all_text_ja() -> dict[str, str]:
    """definitions + 同梱 overlay 全部の質問 leaf の text_ja を集める。

    overlay は手動列挙でなく examples/overlays/ を走査する(列挙漏れ防止)。
    """
    sources = [
        four_layer_path(),
        matrix_path(),
        transition_path(),
        task_contract_path(),
        patch_ownership_path(),
        *sorted((EXAMPLES_DIR / "overlays").rglob("*.yaml")),
    ]
    out: dict[str, str] = {}
    for p in sources:
        data = ov.load_yaml(p)
        items = data.get("items") or data.get("add") or []
        for item in items:
            if isinstance(item, dict) and "text_ja" in item and "id" in item:
                out[item["id"]] = item["text_ja"]
    return out


_ANSWER_LINE_RE = re.compile(r"^\s*([\w.]+): \S")


def _data_label_ja() -> dict[str, str]:
    """data leaf(scorer.type 等)の label_ja を定義から集める(ドリフト検査用)。"""
    out: dict[str, str] = {}
    for path in (task_contract_path(), patch_ownership_path()):
        data = ov.load_yaml(path)
        out.update({
            item["id"]: " ".join(str(item["label_ja"]).split())
            for item in data.get("items", [])
            if isinstance(item, dict) and item.get("kind") == "data" and "label_ja" in item
        })
    return out


_DATA_LABEL_JA = _data_label_ja()


def test_all_text_ja_yaml_twinの問コメントと比較した場合_ドリフトがないこと():
    # Arrange
    text_ja = _all_text_ja()
    from conftest import sample_business_yaml_twin_path

    path = sample_business_yaml_twin_path()
    checked = 0
    problems: list[str] = []

    # Act
    for lineno, line in enumerate(path.read_text().splitlines(), 1):
        loc = f"{path.name}:{lineno}"
        qm = _QUESTION_COMMENT_RE.match(line)
        if qm:
            qid, comment = qm.group(1), qm.group(2).strip()
            if qid not in text_ja:
                problems.append(f"{loc}: unknown id with 問 comment: {qid}")
                continue
            checked += 1
            if comment != text_ja[qid]:
                problems.append(
                    f"{loc}: drifted comment for {qid}\n"
                    f"    comment: {comment}\n    text_ja: {text_ja[qid]}"
                )
            continue
        am = _ANSWER_LINE_RE.match(line)
        if am and am.group(1) in text_ja and "# 問:" not in line:
            problems.append(f"{loc}: answer line for {am.group(1)} lacks 問 comment")

    # Assert
    assert checked >= 20, f"question comments not found (checked={checked})"
    assert not problems, "yaml twin drift:\n" + "\n".join(problems)


def test_all_text_ja_csv質問列と比較した場合_ドリフトがないこと():
    """問いの正本は definitions/overlay に一元化されているので、CSV 側の質問列は
    複製 — このテストが改変・改定漏れ・id タイプミスを検出する。
    """
    # Arrange
    import csv as _csv
    import io as _io

    text_ja = _all_text_ja()
    reserved = {"target", "task", "patch", "description"}
    checked = 0
    problems: list[str] = []
    csv_files = sorted(EXAMPLES_DIR.rglob("*.csv"))
    assert len(csv_files) >= 10, "expected the bundled CSV samples"

    # Act
    for path in csv_files:
        text = path.read_bytes().decode("utf-8-sig")
        for lineno, row in enumerate(_csv.reader(_io.StringIO(text, newline="")), 1):
            if lineno == 1 or not row or not row[0]:
                continue
            rid = row[0].strip()
            if rid in reserved:
                continue
            loc = f"{path.relative_to(EXAMPLES_DIR)}:{lineno}"
            question = (row[1] if len(row) > 1 else "").strip()
            if rid not in text_ja:
                # data leaf(scorer.type 等)はラベル列。label_ja と照合する
                if rid in _DATA_LABEL_JA:
                    checked += 1
                    if question != _DATA_LABEL_JA[rid]:
                        problems.append(
                            f"{loc}: drifted data label for {rid}\n"
                            f"    csv:      {question}\n    label_ja: {_DATA_LABEL_JA[rid]}"
                        )
                    continue
                problems.append(f"{loc}: unknown question id: {rid}")
                continue
            checked += 1
            if question != text_ja[rid]:
                problems.append(
                    f"{loc}: drifted question column for {rid}\n"
                    f"    csv:     {question}\n    text_ja: {text_ja[rid]}"
                )

    # Assert
    assert checked > 50, f"question rows not found in CSVs (checked={checked})"
    assert not problems, "csv/definition drift:\n" + "\n".join(problems)


def test_examples_csv_全同梱sampleを検査した場合_UTF8BOMかつCRLFであること():
    """examples/README の公開契約: 全サンプルを Excel でそのまま開ける。"""
    # Arrange
    csv_files = sorted(EXAMPLES_DIR.rglob("*.csv"))
    problems: list[str] = []

    # Act
    for path in csv_files:
        raw = path.read_bytes()
        relative = path.relative_to(EXAMPLES_DIR)
        if not raw.startswith(b"\xef\xbb\xbf"):
            problems.append(f"{relative}: missing UTF-8 BOM")
        if b"\n" in raw.replace(b"\r\n", b""):
            problems.append(f"{relative}: contains LF-only line endings")

    # Assert
    assert csv_files
    assert not problems, "CSV encoding drift:\n" + "\n".join(problems)
