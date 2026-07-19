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


def test_unknown_target_raises():
    with pytest.raises(ValueError):
        ii.generate("nope")


# --- 同梱 examples の「問:」コメントが定義の text_ja とドリフトしていないこと ---

_QUESTION_COMMENT_RE = re.compile(r"^\s*([\w.]+):[^#\n]*#\s*問:\s*(.+?)(?:\s*→.*)?$")


def _all_text_ja() -> dict[str, str]:
    """definitions + 同梱 overlay の全質問 leaf の text_ja を集める。"""
    sources = [
        four_layer_path(),
        matrix_path(),
        transition_path(),
        task_contract_path(),
        sample_overlay_path(),
        hs_overlay_four_layer_path(),
        insourcing_overlay_path(),
    ]
    out: dict[str, str] = {}
    for p in sources:
        data = ov.load_yaml(p)
        items = data.get("items") or data.get("add") or []
        for item in items:
            if isinstance(item, dict) and "text_ja" in item and "id" in item:
                out[item["id"]] = item["text_ja"]
    return out


def test_example_question_comments_match_definitions():
    """examples の `# 問: ...` コメントは正本(text_ja)と一致しなければならない。

    問いの正本は definitions/overlay に一元化されているので、examples 側の
    コメントは複製 — このテストがドリフト(改変・改定漏れ)を検出する。
    """
    text_ja = _all_text_ja()
    checked = 0
    mismatches: list[str] = []
    for path in list(EXAMPLES_DIR.rglob("*.yaml")):
        if "overlays" in path.parts:
            continue  # overlay ファイル自身は正本側
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            m = _QUESTION_COMMENT_RE.match(line)
            if not m:
                continue
            qid, comment = m.group(1), m.group(2).strip()
            if qid not in text_ja:
                continue
            checked += 1
            if comment != text_ja[qid]:
                mismatches.append(
                    f"{path.relative_to(EXAMPLES_DIR)}:{lineno}: {qid}\n"
                    f"    comment: {comment}\n    text_ja: {text_ja[qid]}"
                )
    assert checked > 50, f"question comments not found in examples (checked={checked})"
    assert not mismatches, "drifted question comments:\n" + "\n".join(mismatches)
