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
    sample_overlay_path,
    task_contract_path,
    transition_path,
)

_DEF_PATHS = {
    "four-layer": four_layer_path,
    "matrix": matrix_path,
    "transition": transition_path,
    "task-contract": task_contract_path,
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


@pytest.mark.parametrize("target", sorted(ii.TARGETS))
def test_template_is_valid_yaml_and_covers_all_questions(target):
    text = ii.generate(target)
    data = yaml.safe_load(text)
    assert isinstance(data, dict)
    filename, exclude = ii.TARGETS[target]
    expected = _question_ids(_DEF_PATHS[target](), exclude)
    # 質問 id はテンプレート本文に必ず現れる(値は空 = 未回答)
    for qid in expected:
        assert f"{qid}:" in text, f"{target}: template misses {qid}"
    # 問いコメントは text_ja 由来
    assert "# 問: " in text


def test_template_includes_overlay_added_questions():
    text = ii.generate("four-layer", overlay_paths=[sample_overlay_path()])
    assert "L1.MIDORI_Q5:" in text and "L4.MIDORI_Q6:" in text
    assert "法務のレビュー" in text  # overlay の text_ja がコメントに出る
    # overlay 付き出力も valid YAML であること
    assert isinstance(yaml.safe_load(text), dict)


def test_task_contract_template_includes_data_leaves():
    """scorer.type / scorer.iruler_double_eval(kind: data)もテンプレートに出る。

    これが欠けたテンプレートは check-task-contract で exit 3 になる。"""
    text = ii.generate("task-contract")
    assert "scorer.type:" in text
    assert "scorer.iruler_double_eval:" in text


def test_multiline_text_ja_overlay_still_generates_valid_yaml(tmp_path):
    """複数行 text_ja を持つ正当な overlay からも不正 YAML を生成しない。"""
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
    text = ii.generate("four-layer", overlay_paths=[ov_path])
    data = yaml.safe_load(text)  # ParserError にならないこと
    assert isinstance(data, dict)
    assert "一行目 二行目: 詳細" in text  # 1 行に正規化される


def test_four_layer_template_orders_gating_before_parallel():
    """overlay で追加されたゲート層(L5)は並列軸(efficacy 等)より前に出る。"""
    text = ii.generate("four-layer", overlay_paths=[hs_overlay_four_layer_path()])
    pos_l5 = text.index("L5.Q1:")
    pos_eff = text.index("efficacy.E1:")
    pos_org = text.index("organization.C1:")
    assert pos_l5 < pos_eff < pos_org


def test_unknown_target_raises():
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


def test_example_question_comments_match_definitions():
    """残す YAML 記入例(双子 1 本)の「問:」コメントが正本と一致すること。"""
    text_ja = _all_text_ja()
    from conftest import sample_business_yaml_twin_path

    path = sample_business_yaml_twin_path()
    checked = 0
    problems: list[str] = []
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
    assert checked >= 20, f"question comments not found (checked={checked})"
    assert not problems, "yaml twin drift:\n" + "\n".join(problems)


def test_example_csv_question_column_matches_definitions():
    """全 CSV サンプルの質問列が正本(text_ja)と一致すること。

    問いの正本は definitions/overlay に一元化されているので、CSV 側の質問列は
    複製 — このテストが改変・改定漏れ・id タイプミスを検出する。
    """
    import csv as _csv
    import io as _io

    text_ja = _all_text_ja()
    reserved = {"target", "task", "description"}
    checked = 0
    problems: list[str] = []
    csv_files = sorted(EXAMPLES_DIR.rglob("*.csv"))
    assert len(csv_files) >= 10, "expected the bundled CSV samples"
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
                # data leaf(scorer.type 等)はラベル列なので text_ja 照合対象外
                if rid in ("scorer.type", "scorer.iruler_double_eval"):
                    continue
                problems.append(f"{loc}: unknown question id: {rid}")
                continue
            checked += 1
            if question != text_ja[rid]:
                problems.append(
                    f"{loc}: drifted question column for {rid}\n"
                    f"    csv:     {question}\n    text_ja: {text_ja[rid]}"
                )
    assert checked > 50, f"question rows not found in CSVs (checked={checked})"
    assert not problems, "csv/definition drift:\n" + "\n".join(problems)
