"""CSV 入出力(io_input)のテスト: ローダ / snapshot 同値性 / 出力 / 安全化。"""
from __future__ import annotations

import csv
import io
import json
import subprocess
from pathlib import Path

import pytest

from adr import io_input as ii
from adr import check_readiness as cr
from adr import check_task_contract as tc
from conftest import (
    EXAMPLES_DIR,
    REPO_ROOT,
    sample_business_path,
    sample_business_yaml_twin_path,
    sample_task_groups_path,
)

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "normalized_inputs.json"
AIDR = REPO_ROOT / "bin" / "aidr"


def _write_csv(tmp_path, rows, name="in.csv", encoding="utf-8-sig"):
    buf = io.StringIO(newline="")
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    p = tmp_path / name
    p.write_bytes(buf.getvalue().encode(encoding))
    return p


SINGLE_OK = [
    ["id", "質問", "回答", "メモ"],
    ["target", "対象業務名", "テスト業務", ""],
    ["L1.Q1", "判断基準は?", "yes", "備考, カンマ入り"],
    ["L1.Q2", "例外は?", "no", ""],
    ["L1.Q3", "", "", ""],  # 空回答 = 未回答
]

WIDE_OK = [
    ["id", "質問", "g1", "g2"],
    ["description", "説明", "グループ1", "グループ2"],
    ["technical_exposure.E1", "問1", "yes", "no"],
    ["technical_exposure.E2", "問2", "", "はい"],
]


# ---------------------------------------------------------------- 正常系

def test_single_csv_normalizes_like_yaml(tmp_path):
    p = _write_csv(tmp_path, SINGLE_OK)
    data, fmt, _rowids = ii.load_input(p, "four-layer")
    assert fmt == "csv"
    assert data == {
        "target": "テスト業務",
        "answers": {"L1.Q1": "yes", "L1.Q2": "no"},
    }


def test_wide_csv_normalizes_entities_in_column_order(tmp_path):
    p = _write_csv(tmp_path, WIDE_OK)
    data, fmt, _rowids = ii.load_input(p, "transition")
    assert fmt == "csv"
    assert data == {
        "task_groups": [
            {"id": "g1", "description": "グループ1",
             "answers": {"technical_exposure.E1": "yes"}},
            {"id": "g2", "description": "グループ2",
             "answers": {"technical_exposure.E1": "no", "technical_exposure.E2": "はい"}},
        ]
    }


def test_yaml_path_returns_yaml_format():
    data, fmt, _rowids = ii.load_input(sample_business_yaml_twin_path(), "four-layer")
    assert fmt == "yaml"
    assert "answers" in data


@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp932"])
def test_encodings_accepted(tmp_path, encoding):
    p = _write_csv(tmp_path, SINGLE_OK, encoding=encoding)
    data, _, _rowids = ii.load_input(p, "four-layer")
    assert data["target"] == "テスト業務"


def test_uppercase_csv_extension(tmp_path):
    p = _write_csv(tmp_path, SINGLE_OK, name="IN.CSV")
    _, fmt, _rowids = ii.load_input(p, "four-layer")
    assert fmt == "csv"


def test_trailing_blank_rows_and_columns_ignored(tmp_path):
    rows = [r + [""] for r in WIDE_OK] + [["", "", "", "", ""]]
    p = _write_csv(tmp_path, rows)
    data, _, _rowids = ii.load_input(p, "transition")
    assert [g["id"] for g in data["task_groups"]] == ["g1", "g2"]


def test_quoted_comma_quote_and_newline_roundtrip(tmp_path):
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", 'カンマ,と"引用"と\n改行', ""],
        ["L1.Q1", "問", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)
    data, _, _rowids = ii.load_input(p, "four-layer")
    assert data["target"] == 'カンマ,と"引用"と\n改行'


# ---------------------------------------------------------------- エラー系

@pytest.mark.parametrize(
    "rows,fragment",
    [
        ([["x", "y"], ["a", "b"]], "must be 'id'"),
        ([["id", "質問", "答え"], ["target", "", "t"]], "回答"),
        ([["id", "質問", "回答"], ["L1.Q1", "", "yes"]], "target"),  # 予約行 0 件
        ([["id", "質問", "回答"], ["target", "", "a"], ["target", "", "b"]], "duplicate"),
        ([["id", "質問", "回答"], ["target", "", "t"], ["L1.Q1", "", "yes"], ["L1.Q1", "", "no"]], "duplicate"),
    ],
)
def test_single_structure_errors(tmp_path, rows, fragment):
    p = _write_csv(tmp_path, rows)
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "four-layer")
    assert fragment in str(e.value)


@pytest.mark.parametrize(
    "rows,fragment",
    [
        ([["id", "質問"], ["technical_exposure.E1", "q"]], "entity column"),
        ([["id", "質問", "g1", "g1"], ["technical_exposure.E1", "q", "yes", "no"]], "unique"),
        ([["id", "質問", "g1"], ["description", "", "a"], ["description", "", "b"]], "duplicate"),
        ([["id", "質問", "g1"], ["technical_exposure.E1", "q", "yes", "stray"]], "beyond"),
    ],
)
def test_wide_structure_errors(tmp_path, rows, fragment):
    p = _write_csv(tmp_path, rows)
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "transition")
    assert fragment in str(e.value)


def test_empty_file_and_bad_bytes(tmp_path):
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")
    with pytest.raises(ii.InputFormatError):
        ii.load_input(p, "four-layer")
    q = tmp_path / "bad.csv"
    q.write_bytes(b"\xff\xfe\x00\x00broken")
    with pytest.raises(ii.InputFormatError):
        ii.load_input(q, "four-layer")


def test_unknown_question_id_rejected_via_command(tmp_path):
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "t", ""],
        ["L1.Q1", "", "yes", ""],
        ["L1.TYPO_Q9", "", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)
    with pytest.raises(ii.InputFormatError) as e:
        cr.check(p)
    assert "L1.TYPO_Q9" in str(e.value)


def test_yaml_unknown_keys_stay_tolerated():
    """YAML は後方互換のため未知キーを従来どおり無視する(twin + 余分キー)。"""
    import yaml as _yaml

    data = _yaml.safe_load(sample_business_yaml_twin_path().read_text())
    data["answers"]["L1.NOT_A_REAL_QUESTION"] = "yes"
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        _yaml.safe_dump(data, f, allow_unicode=True)
    result = cr.check(f.name)
    assert result.conclusion in {"PASS", "REVISE", "BLOCK"}  # エラーにならない


# ---------------------------------------------------------------- snapshot 同値性

def _canon(x):
    if isinstance(x, dict):
        return {k: _canon(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_canon(v) for v in x]
    if isinstance(x, bool):
        return "yes" if x else "no"
    return x


_KIND_BY_DIR = {
    "business": "four-layer",
    "task-contracts": "task-contract",
    "task-groups": "transition",
    "judgments": "matrix",
}


def test_all_csv_samples_match_pre_conversion_snapshot():
    """CSV 化前の YAML 10 本の正規化 dict と、CSV の読込結果が完全一致すること。

    横持ち変換の列ズレや回答の書き換わりを、閾値をまたがなくても検出する。
    after は overlay 回答の分離(CSV は未知 id を拒否するため)で 2 ファイルに
    分かれた: with-overlay 版が snapshot と一致し、無印版は MIDORI 2 問を除いた
    部分集合であることを確認する。
    """
    snap = json.loads(FIXTURE.read_text())
    assert len(snap) == 10
    midori = {"L1.MIDORI_Q5", "L4.MIDORI_Q6"}
    for rel, expected in snap.items():
        kind = _KIND_BY_DIR[Path(rel).parent.name]
        if rel.endswith("sample-expense-approval-after.csv"):
            with_path = REPO_ROOT / rel.replace(
                "sample-expense-approval-after.csv",
                "sample-expense-approval-after-with-overlay.csv",
            )
            data, _, _rowids = ii.load_input(with_path, kind)
            got = _canon(data)
            exp = _canon(expected)
            got["target"] = exp["target"] = ""  # with-overlay 版は対象名だけ変えている
            assert got == exp, rel
            base_data, _, _rowids = ii.load_input(REPO_ROOT / rel, kind)
            base_answers = _canon(base_data)["answers"]
            assert base_answers == {
                k: v for k, v in exp["answers"].items() if k not in midori
            }, rel
            continue
        data, _, _rowids = ii.load_input(REPO_ROOT / rel, kind)
        assert _canon(data) == _canon(expected), rel


def test_yaml_twin_equals_csv_result():
    yaml_result = cr.check(sample_business_yaml_twin_path())
    csv_result = cr.check(sample_business_path())
    assert yaml_result == csv_result


# ---------------------------------------------------------------- 出力 CSV

def test_report_csv_bytes_have_bom_and_no_trailing_blank_line():
    out = subprocess.run(
        [str(AIDR), "screen-transition", str(sample_task_groups_path()), "--format", "csv"],
        capture_output=True,
    )
    assert out.returncode == 0
    assert out.stdout.startswith(b"\xef\xbb\xbf")
    assert not out.stdout.endswith(b"\r\n\r\n")
    text = out.stdout.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0][0] == "record_type"
    assert rows[1][0] == "task_group" and rows[1][2] == "financial_disclosure_draft"


def test_report_csv_record_types_check_readiness():
    out = subprocess.run(
        [str(AIDR), "check-readiness", str(sample_business_path()), "--format", "csv"],
        capture_output=True,
    )
    text = out.stdout.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0][:2] == ["record_type", "target"]
    kinds = {r[0] for r in rows[1:]}
    assert kinds == {"axis", "summary"}
    # 明細行(axis)単体で対象を識別できる(連結集計に耐える)
    axis_targets = {r[1] for r in rows[1:] if r[0] == "axis"}
    assert axis_targets == {"経費精算承認(ミドリ精機・経理部、FY2026 初回診断)"}


def test_formula_cells_neutralized(tmp_path):
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "=HYPERLINK(evil)", ""],
        ["L1.Q1", "", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)
    result = cr.check(p)
    out = cr.render_csv_rows(result)
    # target 列(全行)で中和されている
    assert all(r[1].startswith("'=") for r in out[1:])


def test_entity_id_and_description_neutralized_in_wide_report(tmp_path):
    """横持ち入力のエンティティ id も formula 中和される(レポート側)。"""
    from adr import screen_transition as st

    rows = [
        ["id", "質問", "=1+1"],
        ["description", "説明", "+SUM(A1)"],
    ] + [[qid, "", "no"] for qid in (
        "technical_exposure.E1", "technical_exposure.E2", "technical_exposure.E3",
        "human_necessity.H1", "human_necessity.H2", "human_necessity.H3",
        "demand_elasticity.D1", "demand_elasticity.D2", "demand_elasticity.D3",
    )]
    p = _write_csv(tmp_path, rows)
    result = st.screen(p)
    out = st.render_csv_rows(result)
    row = out[1]
    assert row[2].startswith("'=")   # id 列
    assert row[3].startswith("'+")   # description 列


def test_matrix_csv_ratio_denominator_is_question_total(tmp_path):
    """未回答があっても CSV の分母は質問総数(1/1 で low の矛盾を作らない)。"""
    from adr import score_delegation as sd

    rows = [
        ["id", "質問", "j1"],
        ["description", "説明", "判定1"],
        ["verifiability.V1", "", "yes"],
        ["verifiability.V2", "", ""],
        ["verifiability.V3", "", ""],
        ["answer_definability.A1", "", ""],
        ["answer_definability.A2", "", ""],
        ["answer_definability.A3", "", ""],
    ]
    p = _write_csv(tmp_path, rows)
    result = sd.score(p)
    out = sd.render_csv_rows(result)
    row = out[1]
    assert row[4] == "low" and row[5] == "1/3"
    assert row[6] == "low" and row[7] == "0/3"


def test_unknown_id_with_empty_answer_rejected(tmp_path):
    """回答が空でも、未知 id の行は strict 検証で拒否される(typo の見逃し防止)。"""
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "t", ""],
        ["L1.Q1", "", "yes", ""],
        ["L1.TYPO_Q9", "", "", ""],  # 回答セルは空
    ]
    p = _write_csv(tmp_path, rows)
    with pytest.raises(ii.InputFormatError) as e:
        cr.check(p)
    assert "L1.TYPO_Q9" in str(e.value)


def test_wide_missing_description_row_rejected(tmp_path):
    rows = [
        ["id", "質問", "g1"],
        ["technical_exposure.E1", "", "yes"],
    ]
    p = _write_csv(tmp_path, rows)
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "transition")
    assert "description" in str(e.value)


def test_iruler_accepts_hai(tmp_path):
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["task", "タスク名", "日本語契約", ""],
    ] + [[qid, "", "yes", ""] for qid in (
        "intent.I1", "intent.I2", "intent.I3",
        "boundary.B1", "boundary.B2", "boundary.B3",
        "evidence.E1", "evidence.E2", "evidence.E3",
        "scorer.S1", "scorer.S2",
    )] + [
        ["scorer.type", "", "ai_judge", ""],
        ["scorer.iruler_double_eval", "", "はい", ""],
    ]
    p = _write_csv(tmp_path, rows)
    result = tc.score(p)
    assert result.region == "green"


def test_csv_format_rejected_on_non_report_commands():
    for cmd_args in (
        ["list-definitions", "--format", "csv"],
        ["check-overlay", str(EXAMPLES_DIR / "overlays" / "sample-company" / "extra-rules.yaml"), "--format", "csv"],
    ):
        r = subprocess.run([str(AIDR), *cmd_args], capture_output=True, text=True)
        assert r.returncode == 2  # argparse: invalid choice
        assert "invalid choice" in r.stderr


def test_init_csv_template_roundtrips(tmp_path):
    out = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer", "--format", "csv"],
        capture_output=True,
    )
    assert out.returncode == 0
    assert out.stdout.startswith(b"\xef\xbb\xbf")
    p = tmp_path / "template.csv"
    p.write_bytes(out.stdout)
    data, fmt, _rowids = ii.load_input(p, "four-layer")
    assert fmt == "csv"
    assert data["answers"] == {}  # 全問未回答のテンプレート
    text = out.stdout.decode("utf-8-sig")
    assert "L1.Q1" in text and "判断基準" in text


def test_init_default_stays_yaml():
    """v0.9 互換: --format 無指定の init は YAML テンプレートのまま。"""
    default = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer"], capture_output=True, text=True
    )
    explicit = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer", "--format", "yaml"],
        capture_output=True, text=True,
    )
    assert default.stdout == explicit.stdout
    assert default.stdout.startswith("# aidr check-readiness の入力テンプレート")
