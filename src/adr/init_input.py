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
}


def _merged_definition(target: str, overlay_paths: list) -> dict:
    filename, _ = TARGETS[target]
    base = overlay_mod.load_yaml(_DEFINITIONS_DIR / filename)
    if overlay_paths:
        result = overlay_mod.apply_overlays(base, overlay_paths)
        if not result.ok:
            raise OverlayError(result.violations)
        return result.merged
    return base


def _question_lines(group: dict, indent: str) -> list[str]:
    """1 group 分の質問行(問いコメント付き・値は空 = 未回答)を作る。"""
    lines: list[str] = []
    header = group["header"] or {}
    title = header.get("name_ja") or header.get("name") or ""
    lines.append(f"{indent}# --- {title} ---")
    for leaf in group["leaves"]:
        kind = leaf.get("kind", "question")
        if kind == "question":
            q = leaf.get("text_ja") or leaf.get("text") or ""
            lines.append(f"{indent}{leaf['id']}:     # 問: {q}")
        elif kind == "data":
            label = leaf.get("label", "")
            lines.append(f"{indent}{leaf['id']}:     # {label}")
    return lines


def _axis_groups(target: str, defn: dict) -> dict:
    _, non_question = TARGETS[target]
    groups = overlay_mod.group_items(defn)
    return {gid: g for gid, g in groups.items() if gid not in non_question}


def generate(target: str, overlay_paths: list | None = None) -> str:
    """テンプレート YAML(文字列)を生成する。"""
    if target not in TARGETS:
        raise ValueError(f"unknown target: {target} (choose from {', '.join(TARGETS)})")
    overlay_paths = overlay_paths or []
    defn = _merged_definition(target, overlay_paths)
    groups = _axis_groups(target, defn)

    out: list[str] = []
    if target == "four-layer":
        out += [
            "# aidr check-readiness の入力テンプレート(aidr init --target four-layer で生成)",
            "# 各問いに yes / no を書き込んでください。未回答は unknown(採点上 no)になります。",
            "",
            "target: <対象業務名を書く>",
            "",
            "answers:",
        ]
        for group in groups.values():
            out += _question_lines(group, "  ")
            out.append("")
    elif target == "transition":
        out += [
            "# aidr screen-transition の入力テンプレート(aidr init --target transition で生成)",
            "# 各問いに yes / no を書き込んでください。このコマンドは全問回答が必須です",
            "# (未回答のまま実行すると、欠落 id を列挙したエラーになります)。",
            "# タスク群を増やすときは `- id:` からのブロックを複製してください。",
            "",
            "task_groups:",
            "  - id: <タスク群のスラグを書く>",
            "    description: <タスク群の名前を書く>",
            "    answers:",
        ]
        for group in groups.values():
            out += _question_lines(group, "      ")
            out.append("")
    elif target == "matrix":
        out += [
            "# aidr score-delegation の入力テンプレート(aidr init --target matrix で生成)",
            "# 各問いに yes / no を書き込んでください。未回答は no として採点されます。",
            "# 判定を増やすときは `- id:` からのブロックを複製してください。",
            "",
            "judgments:",
            "  - id: <判定のスラグを書く>",
            "    description: <判定の名前を書く>",
            "    answers:",
        ]
        for group in groups.values():
            out += _question_lines(group, "      ")
            out.append("")
    elif target == "task-contract":
        out += [
            "# aidr check-task-contract の入力テンプレート(aidr init --target task-contract で生成)",
            "# 各問いに yes / no を書き込んでください。scorer.type は必須です",
            "# (human | ai_judge | two_stage。ai_judge のときは scorer.iruler_double_eval も必須)。",
            "",
            "task: <委任するタスク名を書く>",
            "",
            "answers:",
        ]
        for group in groups.values():
            out += _question_lines(group, "  ")
            out.append("")
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n"
