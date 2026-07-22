"""Generate answer-file templates with question comments (``aidr init``).

質問の正本は definitions/*.yaml だけに置き(一元管理)、回答するときは
問いコメント付きの 1 ファイルで完結させる — その両立のためのジェネレータ。
生成されるテンプレートのコメントは定義の ``text_ja``(無ければ ``text``)
から作るので、定義とドリフトしない。同梱の examples/ も「このテンプレートに
回答を書き込んだ体」で維持する。

Usage::

    aidr init --target four-layer    > my-business.yaml
    aidr init --target transition    > my-task-groups.yaml
    aidr init --target matrix        > my-judgments.yaml
    aidr init --target task-contract > my-contract.yaml
    aidr init --target four-layer --overlay our-rules.yaml   # 追加質問も含める
"""

from __future__ import annotations

from pathlib import Path

import overlay_scoring as overlay_mod
from .check_readiness import OverlayError

_DEFINITIONS_DIR = Path(__file__).resolve().parents[2] / "definitions"

# target 名 -> (定義ファイル, 非質問 group)
TARGETS = {
    "four-layer": ("four-layer.yaml", set()),
    "matrix": ("delegation-matrix.yaml", {"regions", "examples"}),
    "transition": ("transition-screening.yaml", {"types", "examples"}),
    "task-contract": ("task-contract.yaml", {"gates", "examples"}),
    "patch-ownership": ("patch-ownership.yaml", {"gates", "examples"}),
}


def _merged_definition(target: str, overlay_paths: list) -> dict:
    filename, _ = TARGETS[target]
    base = overlay_mod.load_yaml(_DEFINITIONS_DIR / filename)
    if overlay_paths:
        if target == "patch-ownership":
            from .check_patch_ownership import merge_definition

            return merge_definition(base, overlay_paths)
        result = overlay_mod.apply_overlays(base, overlay_paths)
        if not result.ok:
            raise OverlayError(result.violations)
        return result.merged
    return base


def _one_line(text) -> str:
    """コメント文を 1 行に正規化する(複数行 text_ja でも不正 YAML を作らない)。"""
    return " ".join(str(text).split())


def _question_lines(group: dict, indent: str) -> list[str]:
    """1 group 分の質問行(問いコメント付き・値は空 = 未回答)を作る。"""
    lines: list[str] = []
    header = group["header"] or {}
    title = header.get("name_ja") or header.get("name") or ""
    lines.append(f"{indent}# --- {title} ---")
    for leaf in group["leaves"]:
        kind = leaf.get("kind", "question")
        if kind == "question":
            q = _one_line(leaf.get("text_ja") or leaf.get("text") or "")
            lines.append(f"{indent}{leaf['id']}:     # 問: {q}")
        elif kind == "data":
            label = _one_line(leaf.get("label_ja") or leaf.get("label") or "")
            lines.append(f"{indent}{leaf['id']}:     # {label}")
    return lines


def _axis_groups(target: str, defn: dict) -> dict:
    _, non_question = TARGETS[target]
    groups = overlay_mod.group_items(defn)
    selected = {gid: g for gid, g in groups.items() if gid not in non_question}
    if target != "four-layer":
        return selected
    # four-layer はゲート層(role 未指定)を先、並列軸(role: parallel)を後に並べる。
    # overlay で追加されたゲート層(例: 高責任 overlay の L5)がマージ順のまま
    # 並列軸の後ろに出ると、積み上げを先に読む構成が崩れるため。
    gating = {
        gid: g for gid, g in selected.items()
        if (g["header"] or {}).get("role") != "parallel"
    }
    parallel = {gid: g for gid, g in selected.items() if gid not in gating}
    return {**gating, **parallel}


# target ごとの YAML テンプレート: (先頭ブロック, 質問行のインデント)。
_YAML_TEMPLATE: dict[str, tuple[list[str], str]] = {
    "four-layer": ([
        "# aidr check-readiness の入力テンプレート(aidr init --target four-layer で生成)",
        "# 各問いに yes / no を書き込んでください。未回答は unknown(採点上 no)になります。",
        "",
        "target: <対象業務名を書く>",
        "",
        "answers:",
    ], "  "),
    "transition": ([
        "# aidr screen-transition の入力テンプレート(aidr init --target transition で生成)",
        "# 各問いに yes / no を書き込んでください。このコマンドは全問回答が必須です",
        "# (未回答のまま実行すると、欠落 id を列挙したエラーになります)。",
        "# タスク群を増やすときは `- id:` からのブロックを複製してください。",
        "",
        "task_groups:",
        "  - id: <タスク群のスラグを書く>",
        "    description: <タスク群の名前を書く>",
        "    answers:",
    ], "      "),
    "matrix": ([
        "# aidr score-delegation の入力テンプレート(aidr init --target matrix で生成)",
        "# 各問いに yes / no を書き込んでください。未回答は no として採点されます。",
        "# 判定を増やすときは `- id:` からのブロックを複製してください。",
        "",
        "judgments:",
        "  - id: <判定のスラグを書く>",
        "    description: <判定の名前を書く>",
        "    answers:",
    ], "      "),
    "task-contract": ([
        "# aidr check-task-contract の入力テンプレート(aidr init --target task-contract で生成)",
        "# 各問いに yes / no を書き込んでください。scorer.type は必須です",
        "# (human | ai_judge | two_stage。ai_judge のときは scorer.iruler_double_eval も必須)。",
        "",
        "task: <委任するタスク名を書く>",
        "",
        "answers:",
    ], "  "),
    "patch-ownership": ([
        "# aidr check-patch-ownership の入力テンプレート(aidr init --target patch-ownership で生成)",
        "# question 行はすべて yes / no を明示してください。data 行も必須条件に従って記入します。",
        "# 証拠参照は content-addressed 形式です。参照先そのものはこのコマンドでは取得しません。",
        "",
        "patch: <パッチ名またはコミットを書く>",
        "",
        "answers:",
    ], "  "),
}


def generate(target: str, overlay_paths: list | None = None) -> str:
    """テンプレート YAML(文字列)を生成する。"""
    if target not in TARGETS:
        raise ValueError(f"unknown target: {target} (choose from {', '.join(TARGETS)})")
    defn = _merged_definition(target, overlay_paths or [])
    groups = _axis_groups(target, defn)

    header, indent = _YAML_TEMPLATE[target]
    out = list(header)
    for group in groups.values():
        out += _question_lines(group, indent)
        out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------- CSV テンプレート

_SINGLE_META = {
    "four-layer": ("target", "対象業務名", "<対象業務名を書く>"),
    "task-contract": ("task", "委任するタスク名", "<委任するタスク名を書く>"),
    "patch-ownership": ("patch", "パッチ名またはコミット", "<パッチ名またはコミットを書く>"),
}
_WIDE_PLACEHOLDER = {
    "transition": "<タスク群の名前を書く>",
    "matrix": "<判定の名前を書く>",
}


def _leaf_prompt(leaf: dict) -> str | None:
    """CSV の質問列に出す文言。出力対象でない leaf は None を返す。"""
    kind = leaf.get("kind", "question")
    if kind == "question":
        return _one_line(leaf.get("text_ja") or leaf.get("text") or "")
    if kind == "data":
        return _one_line(leaf.get("label_ja") or leaf.get("label") or "")
    return None


def generate_csv(target: str, overlay_paths: list | None = None) -> list[list[str]]:
    """CSV テンプレートの行列を生成する(書き出しは io_input.rows_to_csv_bytes)。

    質問列は定義の text_ja(無ければ text)から作るので定義とドリフトしない。
    横持ち(transition / matrix)はエンティティ列 1 本(entity_1)で生成し、
    利用者はスプレッドシート上で列を複製してエンティティを増やす。
    """
    if target not in TARGETS:
        raise ValueError(f"unknown target: {target} (choose from {', '.join(TARGETS)})")
    defn = _merged_definition(target, overlay_paths or [])
    groups = _axis_groups(target, defn)

    def question_rows(prefix_cols: int) -> list[list[str]]:
        rows: list[list[str]] = []
        for group in groups.values():
            for leaf in group["leaves"]:
                cell = _leaf_prompt(leaf)
                if cell is None:
                    continue
                rows.append([leaf["id"], cell] + [""] * prefix_cols)
        return rows

    if target in _SINGLE_META:
        reserved, label, placeholder = _SINGLE_META[target]
        rows = [["id", "質問", "回答", "メモ"], [reserved, label, placeholder, ""]]
        rows += [r[:2] + ["", ""] for r in question_rows(0)]
        return rows

    placeholder = _WIDE_PLACEHOLDER[target]
    rows = [["id", "質問", "entity_1"], ["description", "説明", placeholder]]
    rows += question_rows(1)
    return rows
