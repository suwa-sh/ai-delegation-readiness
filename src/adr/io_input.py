"""入力ファイルの共有ローダ: CSV / YAML を同じ dict 形に正規化する。

CSV は業務側ユーザーの記入フォーマット(スプレッドシートで問いと回答を並べて
書く)、YAML はエンジニア/CI 向けの別形式。どちらも同じ内部形に正規化され、
採点ロジックは形式を意識しない。

CSV スキーマは 2 種類:

単一回答者(kind = "four-layer" / "task-contract")::

    id,質問,回答,メモ
    target,対象業務名,経費精算承認(...),
    L1.Q1,判断基準は...,yes,経費規程あり

  - 消費するのは id と 回答 列のみ(質問は表示用、メモは自由記入)
  - 予約行 ``target``(four-layer)/ ``task``(task-contract)はちょうど 1 件
  - 回答が空 = 未回答(キーごと省略される)

複数エンティティ・横持ち(kind = "transition" / "matrix")::

    id,質問,financial_disclosure_draft,expense_entry_check
    description,説明,決算開示資料のドラフト,経費精算チェック
    technical_exposure.E1,タスク時間の過半が...,yes,yes

  - ヘッダ 3 列目以降 = エンティティ id(列の複製でエンティティを増やす)
  - 予約行 ``description`` は最大 1 件
  - エンティティ列は 1 本以上が必須(0 本 = 「何も診断せず成功」の穴を塞ぐ)

Excel 由来の揺れは吸収する: UTF-8 BOM / cp932 / CRLF / 末尾の空行・空列 /
セル前後の空白。一方で「静かな誤採点」につながる崩れは拒否する:
行 id の重複・予約行の欠落や重複・エンティティ列名の空/重複/改行入り。
未知の質問 id の検証は overlay 適用後の定義が必要なため、各コマンド側が
:func:`validate_known_ids` で行う(CSV 入力のときのみ)。
"""

from __future__ import annotations

import csv
import io
from pathlib import Path

import overlay_scoring as overlay_mod


class InputFormatError(Exception):
    """CSV 入力の構造が契約を満たしていない(CLI は exit 3 で報告する)。"""


# kind ごとの正規化形: (形式, 予約行 id, 返す dict のキー)
_SINGLE_KINDS = {
    "four-layer": ("target", "target"),
    "task-contract": ("task", "task"),
}
_WIDE_KINDS = {
    "transition": "task_groups",
    "matrix": "judgments",
}
KINDS = tuple(_SINGLE_KINDS) + tuple(_WIDE_KINDS)

_DESCRIPTION_ROW = "description"


def load_input(path: str | Path, kind: str) -> tuple[dict, str, list[str] | None]:
    """入力を読み、(正規化 dict, 形式 "csv"|"yaml", CSV の質問行 id) を返す。

    正規化 dict は既存の YAML 入力とまったく同じ形なので、呼び出し側の
    採点ロジック・バリデーションは形式を意識しない。

    第 3 要素は CSV のときのみ: 予約行を除く**全質問行の id**(回答が空の行も
    含む)。strict 検証はこれを定義と照合する — 回答済み id だけを照合すると、
    「typo した行に回答したが空欄のまま」のような未知 id 行が素通りするため。
    YAML のときは None(後方互換の寛容契約)。
    """
    if kind not in KINDS:
        raise ValueError(f"unknown input kind: {kind} (choose from {', '.join(KINDS)})")
    path = Path(path)
    if path.suffix.lower() == ".csv":
        data, row_ids = _load_csv(path, kind)
        return data, "csv", row_ids
    return overlay_mod.load_yaml(path), "yaml", None


def collect_question_ids(defn: dict, non_question_groups: set[str]) -> set[str]:
    """overlay 適用後の定義から、回答キーとして正当な id の集合を作る。

    質問 leaf(kind 未指定 = question)に加えて、data leaf(scorer.type 等)も
    回答ファイルに書かれる正当なキーなので含める。
    """
    groups = overlay_mod.group_items(defn)
    ids: set[str] = set()
    for gid, group in groups.items():
        if gid in non_question_groups:
            continue
        for leaf in group["leaves"]:
            if leaf.get("kind", "question") in ("question", "data"):
                ids.add(leaf["id"])
    return ids


def validate_known_ids(answer_ids, known_ids: set[str], source: str) -> None:
    """CSV 入力の回答 id を定義と照合する(typo の静かな誤採点を防ぐ)。"""
    unknown = sorted(set(answer_ids) - known_ids)
    if unknown:
        raise InputFormatError(
            f"{source}: unknown question id(s): {', '.join(unknown)} "
            "(check for typos against the definition)"
        )


# ---------------------------------------------------------------- CSV 読込

def _read_csv_rows(path: Path) -> list[list[str]]:
    raw = path.read_bytes()
    if not raw.strip():
        raise InputFormatError(f"{path.name}: file is empty")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = raw.decode("cp932")
        except UnicodeDecodeError as e:
            raise InputFormatError(
                f"{path.name}: cannot decode as UTF-8 or CP932 (Shift_JIS)"
            ) from e
    rows = list(csv.reader(io.StringIO(text, newline="")))
    # セル前後の空白を strip し、末尾の空行を落とす
    rows = [[cell.strip() for cell in row] for row in rows]
    while rows and not any(rows[-1]):
        rows.pop()
    if not rows:
        raise InputFormatError(f"{path.name}: no data rows")
    return rows


def _pad(row: list[str], width: int) -> list[str]:
    return row + [""] * (width - len(row)) if len(row) < width else row


def _load_csv(path: Path, kind: str) -> tuple[dict, list[str]]:
    rows = _read_csv_rows(path)
    header = rows[0]
    if not header or header[0] != "id":
        raise InputFormatError(
            f"{path.name}: first header cell must be 'id' (got: {header[0] if header else '<empty>'})"
        )
    if kind in _SINGLE_KINDS:
        return _load_single(path, rows, kind)
    return _load_wide(path, rows, kind)


def _load_single(path: Path, rows: list[list[str]], kind: str) -> tuple[dict, list[str]]:
    reserved, out_key = _SINGLE_KINDS[kind]
    header = rows[0]
    if len(header) < 3 or header[2] != "回答":
        raise InputFormatError(
            f"{path.name}: header must be 'id,質問,回答[,メモ]' (third column must be 回答)"
        )
    answers: dict[str, str] = {}
    meta: list[str] = []
    seen: set[str] = set()
    row_ids: list[str] = []
    for lineno, row in enumerate(rows[1:], 2):
        row = _pad(row, 3)
        rid, answer = row[0], row[2]
        if not rid:
            if any(row):
                raise InputFormatError(f"{path.name}:{lineno}: row has values but no id")
            continue  # 完全な空行
        if rid in seen:
            raise InputFormatError(f"{path.name}:{lineno}: duplicate row id '{rid}'")
        seen.add(rid)
        if rid == reserved:
            meta.append(answer)
            continue
        row_ids.append(rid)
        if answer != "":
            answers[rid] = answer
    if len(meta) != 1:
        raise InputFormatError(
            f"{path.name}: expected exactly one '{reserved}' row, found {len(meta)}"
        )
    return {out_key: meta[0], "answers": answers}, row_ids


def _load_wide(path: Path, rows: list[list[str]], kind: str) -> tuple[dict, list[str]]:
    out_key = _WIDE_KINDS[kind]
    header = rows[0]
    # 末尾の空ヘッダ列(Excel の余剰列)は落とす。内部の空ヘッダ列はエラー。
    while len(header) > 2 and header[-1] == "":
        header = header[:-1]
    entity_ids = header[2:]
    if not entity_ids:
        raise InputFormatError(
            f"{path.name}: at least one entity column is required "
            "(add your task-group/judgment ids as columns after 'id,質問')"
        )
    bad = [e for e in entity_ids if not e or "\n" in e or "\r" in e]
    if bad or len(set(entity_ids)) != len(entity_ids):
        raise InputFormatError(
            f"{path.name}: entity column names must be non-empty, unique, single-line "
            f"(got: {entity_ids})"
        )
    width = len(header)
    descriptions: dict[str, str] = {}
    answers: dict[str, dict[str, str]] = {e: {} for e in entity_ids}
    desc_rows = 0
    seen: set[str] = set()
    row_ids: list[str] = []
    for lineno, row in enumerate(rows[1:], 2):
        row = _pad(row, width)
        if any(row[width:]):
            raise InputFormatError(
                f"{path.name}:{lineno}: row has non-empty cells beyond the entity columns"
            )
        rid = row[0]
        if not rid:
            if any(row):
                raise InputFormatError(f"{path.name}:{lineno}: row has values but no id")
            continue
        if rid in seen:
            raise InputFormatError(f"{path.name}:{lineno}: duplicate row id '{rid}'")
        seen.add(rid)
        if rid == _DESCRIPTION_ROW:
            desc_rows += 1
            for e, cell in zip(entity_ids, row[2:width]):
                descriptions[e] = cell
            continue
        row_ids.append(rid)
        for e, cell in zip(entity_ids, row[2:width]):
            if cell != "":
                answers[e][rid] = cell
    if desc_rows != 1:
        # init テンプレートは必ず description 行を出す。0 件 = 行の消し込み事故の
        # 可能性が高いので、Excel 事故に厳格の方針どおりちょうど 1 件を要求する。
        raise InputFormatError(
            f"{path.name}: expected exactly one 'description' row, found {desc_rows}"
        )
    entries = [
        {"id": e, "description": descriptions.get(e, e), "answers": answers[e]}
        for e in entity_ids
    ]
    return {out_key: entries}, row_ids


# ---------------------------------------------------------------- CSV 書出

def sanitize_cell(value: str) -> str:
    """外部入力由来のセルを Excel の数式評価から守る(OWASP 方式)。

    ``=`` ``+`` ``-`` ``@`` タブ・CR で始まる値は先頭に ``'`` を付けて中和する。
    """
    if value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def rows_to_csv_bytes(rows: list[list[str]]) -> bytes:
    """CSV 行列を UTF-8 BOM 付き bytes にする(ロケール非依存)。"""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\r\n")
    writer.writerows(rows)
    return b"\xef\xbb\xbf" + buf.getvalue().encode("utf-8")


def write_csv_stdout(rows: list[list[str]]) -> None:
    """CSV を stdout に BOM 付き bytes で書く(print のロケール依存を回避)。"""
    import sys

    sys.stdout.flush()
    sys.stdout.buffer.write(rows_to_csv_bytes(rows))
    sys.stdout.buffer.flush()
