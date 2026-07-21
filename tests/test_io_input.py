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

def test_load_input_単一レイヤーCSVの場合_YAMLと同じ形に正規化されること(tmp_path):
    # Arrange
    p = _write_csv(tmp_path, SINGLE_OK)

    # Act
    data, fmt, _rowids = ii.load_input(p, "four-layer")

    # Assert
    assert fmt == "csv"
    assert data == {
        "target": "テスト業務",
        "answers": {"L1.Q1": "yes", "L1.Q2": "no"},
    }


def test_load_input_横持ちCSVの場合_列順でエンティティが正規化されること(tmp_path):
    # Arrange
    p = _write_csv(tmp_path, WIDE_OK)

    # Act
    data, fmt, _rowids = ii.load_input(p, "transition")

    # Assert
    assert fmt == "csv"
    assert data == {
        "task_groups": [
            {"id": "g1", "description": "グループ1",
             "answers": {"technical_exposure.E1": "yes"}},
            {"id": "g2", "description": "グループ2",
             "answers": {"technical_exposure.E1": "no", "technical_exposure.E2": "はい"}},
        ]
    }


def test_load_input_YAMLパスを渡した場合_フォーマットがyamlになること():
    # Act
    data, fmt, _rowids = ii.load_input(sample_business_yaml_twin_path(), "four-layer")

    # Assert
    assert fmt == "yaml"
    assert "answers" in data


@pytest.mark.parametrize(
    "encoding",
    ["utf-8", "utf-8-sig", "cp932"],
    ids=[
        "utf-8の場合_正しく読み込まれること",
        "utf-8-sigの場合_正しく読み込まれること",
        "cp932の場合_正しく読み込まれること",
    ],
)
def test_load_input_対応エンコーディングの場合_正しく読み込まれること(tmp_path, encoding):
    # Arrange
    p = _write_csv(tmp_path, SINGLE_OK, encoding=encoding)

    # Act
    data, _, _rowids = ii.load_input(p, "four-layer")

    # Assert
    assert data["target"] == "テスト業務"


def test_load_input_拡張子が大文字の場合_csv形式と判定されること(tmp_path):
    # Arrange
    p = _write_csv(tmp_path, SINGLE_OK, name="IN.CSV")

    # Act
    _, fmt, _rowids = ii.load_input(p, "four-layer")

    # Assert
    assert fmt == "csv"


def test_load_input_末尾に空行空列がある場合_無視されること(tmp_path):
    # Arrange
    rows = [r + [""] for r in WIDE_OK] + [["", "", "", "", ""]]
    p = _write_csv(tmp_path, rows)

    # Act
    data, _, _rowids = ii.load_input(p, "transition")

    # Assert
    assert [g["id"] for g in data["task_groups"]] == ["g1", "g2"]


def test_load_input_カンマ引用符改行を含むセルの場合_そのまま復元されること(tmp_path):
    # Arrange
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", 'カンマ,と"引用"と\n改行', ""],
        ["L1.Q1", "問", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)

    # Act
    data, _, _rowids = ii.load_input(p, "four-layer")

    # Assert
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
    ids=[
        "id列名が不正な場合_InputFormatErrorになること",
        "回答列が欠落した場合_InputFormatErrorになること",
        "target行がない場合_InputFormatErrorになること",
        "targetが重複した場合_InputFormatErrorになること",
        "質問idが重複した場合_InputFormatErrorになること",
    ],
)
def test_load_input_単一レイヤーCSVの構造が不正な場合_InputFormatErrorになること(tmp_path, rows, fragment):
    # Arrange
    p = _write_csv(tmp_path, rows)

    # Act
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "four-layer")

    # Assert
    assert fragment in str(e.value)


@pytest.mark.parametrize(
    "rows,fragment",
    [
        ([["id", "質問"], ["technical_exposure.E1", "q"]], "entity column"),
        ([["id", "質問", "g1", "g1"], ["technical_exposure.E1", "q", "yes", "no"]], "unique"),
        ([["id", "質問", "g1"], ["description", "", "a"], ["description", "", "b"]], "duplicate"),
        ([["id", "質問", "g1"], ["technical_exposure.E1", "q", "yes", "stray"]], "beyond"),
    ],
    ids=[
        "エンティティ列がない場合_InputFormatErrorになること",
        "グループ列名が重複した場合_InputFormatErrorになること",
        "説明行が重複した場合_InputFormatErrorになること",
        "列数を超えた値がある場合_InputFormatErrorになること",
    ],
)
def test_load_input_横持ちCSVの構造が不正な場合_InputFormatErrorになること(tmp_path, rows, fragment):
    # Arrange
    p = _write_csv(tmp_path, rows)

    # Act
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "transition")

    # Assert
    assert fragment in str(e.value)


def test_load_input_空ファイルや不正バイト列の場合_InputFormatErrorになること(tmp_path):
    # Arrange
    p = tmp_path / "empty.csv"
    p.write_bytes(b"")

    # Act & Assert
    with pytest.raises(ii.InputFormatError):
        ii.load_input(p, "four-layer")

    # Arrange
    q = tmp_path / "bad.csv"
    q.write_bytes(b"\xff\xfe\x00\x00broken")

    # Act & Assert
    with pytest.raises(ii.InputFormatError):
        ii.load_input(q, "four-layer")


def test_check_未知の質問idを含む場合_InputFormatErrorになること(tmp_path):
    # Arrange
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "t", ""],
        ["L1.Q1", "", "yes", ""],
        ["L1.TYPO_Q9", "", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)

    # Act
    with pytest.raises(ii.InputFormatError) as e:
        cr.check(p)

    # Assert
    assert "L1.TYPO_Q9" in str(e.value)


def test_check_YAMLに未知キーがある場合_エラーにならず許容されること():
    """YAML は後方互換のため未知キーを従来どおり無視する(twin + 余分キー)。"""
    import yaml as _yaml

    # Arrange
    data = _yaml.safe_load(sample_business_yaml_twin_path().read_text())
    data["answers"]["L1.NOT_A_REAL_QUESTION"] = "yes"
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        _yaml.safe_dump(data, f, allow_unicode=True)

    # Act
    result = cr.check(f.name)

    # Assert
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


def test_load_input_CSV化前後のサンプル10本を読み込んだ場合_変換前スナップショットと一致すること():
    """横持ち変換の列ズレや回答の書き換わりを、閾値をまたがなくても検出する。

    after は overlay 回答の分離(CSV は未知 id を拒否するため)で 2 ファイルに
    分かれた: with-overlay 版が snapshot と一致し、無印版は MIDORI 2 問を除いた
    部分集合であることを確認する。
    """
    # Arrange
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
            # Act
            data, _, _rowids = ii.load_input(with_path, kind)
            got = _canon(data)
            exp = _canon(expected)
            got["target"] = exp["target"] = ""  # with-overlay 版は対象名だけ変えている

            # Assert
            assert got == exp, rel
            base_data, _, _rowids = ii.load_input(REPO_ROOT / rel, kind)
            base_answers = _canon(base_data)["answers"]
            assert base_answers == {
                k: v for k, v in exp["answers"].items() if k not in midori
            }, rel
            continue

        # Act
        data, _, _rowids = ii.load_input(REPO_ROOT / rel, kind)

        # Assert
        assert _canon(data) == _canon(expected), rel


def test_check_YAML双子とCSVを渡した場合_結果が一致すること():
    # Act
    yaml_result = cr.check(sample_business_yaml_twin_path())
    csv_result = cr.check(sample_business_path())

    # Assert
    assert yaml_result == csv_result


# ---------------------------------------------------------------- 出力 CSV

def test_aidr_screen_transition_csv出力の場合_BOM付きで末尾空行がないこと():
    # Act
    out = subprocess.run(
        [str(AIDR), "screen-transition", str(sample_task_groups_path()), "--format", "csv"],
        capture_output=True,
    )

    # Assert
    assert out.returncode == 0
    assert out.stdout.startswith(b"\xef\xbb\xbf")
    assert not out.stdout.endswith(b"\r\n\r\n")
    text = out.stdout.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0][0] == "record_type"
    assert rows[1][0] == "task_group" and rows[1][2] == "financial_disclosure_draft"


def test_aidr_check_readiness_csv出力の場合_record_typeがaxisとsummaryになること():
    # Act
    out = subprocess.run(
        [str(AIDR), "check-readiness", str(sample_business_path()), "--format", "csv"],
        capture_output=True,
    )

    # Assert
    text = out.stdout.decode("utf-8-sig")
    rows = list(csv.reader(io.StringIO(text, newline="")))
    assert rows[0][:2] == ["record_type", "target"]
    kinds = {r[0] for r in rows[1:]}
    assert kinds == {"axis", "summary"}
    # 明細行(axis)単体で対象を識別できる(連結集計に耐える)
    axis_targets = {r[1] for r in rows[1:] if r[0] == "axis"}
    assert axis_targets == {"経費精算承認(ミドリ精機・経理部、FY2026 初回診断)"}


def test_render_csv_rows_target列に数式がある場合_中和されること(tmp_path):
    # Arrange
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "=HYPERLINK(evil)", ""],
        ["L1.Q1", "", "yes", ""],
    ]
    p = _write_csv(tmp_path, rows)

    # Act
    result = cr.check(p)
    out = cr.render_csv_rows(result)

    # Assert
    # target 列(全行)で中和されている
    assert all(r[1].startswith("'=") for r in out[1:])


def test_render_csv_rows_横持ち入力のエンティティidに数式がある場合_中和されること(tmp_path):
    from adr import screen_transition as st

    # Arrange
    rows = [
        ["id", "質問", "=1+1"],
        ["description", "説明", "+SUM(A1)"],
    ] + [[qid, "", "no"] for qid in (
        "technical_exposure.E1", "technical_exposure.E2", "technical_exposure.E3",
        "human_necessity.H1", "human_necessity.H2", "human_necessity.H3",
        "demand_elasticity.D1", "demand_elasticity.D2", "demand_elasticity.D3",
    )]
    p = _write_csv(tmp_path, rows)

    # Act
    result = st.screen(p)
    out = st.render_csv_rows(result)
    row = out[1]

    # Assert
    assert row[2].startswith("'=")   # id 列
    assert row[3].startswith("'+")   # description 列


def test_render_csv_rows_未回答がある場合_分母が質問総数になること(tmp_path):
    """1/1 で low の矛盾を作らないため。"""
    from adr import score_delegation as sd

    # Arrange
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

    # Act
    result = sd.score(p)
    out = sd.render_csv_rows(result)
    row = out[1]

    # Assert
    assert row[4] == "low" and row[5] == "1/3"
    assert row[6] == "low" and row[7] == "0/3"


def test_check_未知idの回答が空の場合_InputFormatErrorになること(tmp_path):
    """typo の見逃し防止のため。"""
    # Arrange
    rows = [
        ["id", "質問", "回答", "メモ"],
        ["target", "対象業務名", "t", ""],
        ["L1.Q1", "", "yes", ""],
        ["L1.TYPO_Q9", "", "", ""],  # 回答セルは空
    ]
    p = _write_csv(tmp_path, rows)

    # Act
    with pytest.raises(ii.InputFormatError) as e:
        cr.check(p)

    # Assert
    assert "L1.TYPO_Q9" in str(e.value)


def test_load_input_横持ちでdescription行がない場合_InputFormatErrorになること(tmp_path):
    # Arrange
    rows = [
        ["id", "質問", "g1"],
        ["technical_exposure.E1", "", "yes"],
    ]
    p = _write_csv(tmp_path, rows)

    # Act
    with pytest.raises(ii.InputFormatError) as e:
        ii.load_input(p, "transition")

    # Assert
    assert "description" in str(e.value)


def test_score_iruler_double_evalにはいを指定した場合_green判定になること(tmp_path):
    # Arrange
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

    # Act
    result = tc.score(p)

    # Assert
    assert result.region == "green"


def test_aidr_レポート以外のコマンドでcsv形式を指定した場合_拒否されること():
    # Act
    for cmd_args in (
        ["list-definitions", "--format", "csv"],
        ["check-overlay", str(EXAMPLES_DIR / "overlays" / "sample-company" / "extra-rules.yaml"), "--format", "csv"],
    ):
        r = subprocess.run([str(AIDR), *cmd_args], capture_output=True, text=True)

        # Assert
        assert r.returncode == 2  # argparse: invalid choice
        assert "invalid choice" in r.stderr


def test_aidr_init_csv形式のテンプレートを生成した場合_読み込みで往復すること(tmp_path):
    # Act
    out = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer", "--format", "csv"],
        capture_output=True,
    )

    # Assert
    assert out.returncode == 0
    assert out.stdout.startswith(b"\xef\xbb\xbf")
    p = tmp_path / "template.csv"
    p.write_bytes(out.stdout)
    data, fmt, _rowids = ii.load_input(p, "four-layer")
    assert fmt == "csv"
    assert data["answers"] == {}  # 全問未回答のテンプレート
    text = out.stdout.decode("utf-8-sig")
    assert "L1.Q1" in text and "判断基準" in text


def test_aidr_init_format未指定の場合_YAML互換のまま出力されること():
    """v0.9 との後方互換のため。"""
    # Act
    default = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer"], capture_output=True, text=True
    )
    explicit = subprocess.run(
        [str(AIDR), "init", "--target", "four-layer", "--format", "yaml"],
        capture_output=True, text=True,
    )

    # Assert
    assert default.stdout == explicit.stdout
    assert default.stdout.startswith("# aidr check-readiness の入力テンプレート")
