"""Command-line entry point for ``aidr``.

Subcommands:
    init                   generate an answer-file template with question comments
    screen-transition      pre-delegation screening into the 4 AI-transition types
    check-readiness        4-layer + efficacy readiness check (delegate-or-not)
    score-delegation       delegation matrix scoring per judgment
    check-task-contract    execution rubric per delegated task (intent/boundary/evidence/scorer)
    check-patch-ownership  post-generation acceptance gate for an AI-generated patch
    summarize-patch-decisions  discard rate / decided rate over recorded patch decisions
    assess-risk-architecture   org-side adequacy check (detect/contain/escalate per failure scenario)
    validate-audit-log     JSON Schema validation (minimum or extended)
    check-overlay          overlay merge-rule validation
    list-definitions       inspect loaded base + overlay structure
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version

import overlay_scoring

from . import (
    assess_risk_architecture as _risk,
    check_overlay as _check_overlay,
    check_patch_ownership as _patch,
    check_readiness as _check_readiness,
    check_task_contract as _task,
    init_input as _init,
    io_input as _io,
    list_definitions as _list,
    score_delegation as _score,
    screen_transition as _screen,
    summarize_patch_decisions as _decisions,
    validate_audit_log as _validate,
)


def _version_string() -> str:
    """`aidr --version` reports the app version and the overlay engine version.

    The engine version is the primary way to see which overlay-scoring-skeleton
    release this build depends on (requirement: engine version visibility).
    """
    try:
        app = _pkg_version("ai-delegation-readiness")
    except PackageNotFoundError:  # running from a source checkout
        app = "0.0.0.dev0"
    return f"aidr {app} (overlay-scoring-skeleton {overlay_scoring.__version__})"


def _shared_overlay_args(
    parser: argparse.ArgumentParser,
    formats: tuple[str, ...] = ("text", "json"),
) -> None:
    # formats はコマンドごとに指定する: レポートの CSV 対応は採点系 + validate +
    # 採否集計 + 組織体制の 7 コマンドのみ(list-definitions 等の階層構造出力に csv を漏らさない)。
    parser.add_argument(
        "--overlay",
        action="append",
        default=[],
        metavar="PATH",
        help="Overlay file to apply (repeatable; applied in order)",
    )
    parser.add_argument(
        "--format",
        choices=list(formats),
        default="text",
        help="Output format (default: text)",
    )


_REPORT_FORMATS = ("text", "json", "csv")


def _emit(result, args, module) -> None:
    """text / json / csv の共通出力(csv は BOM 付き bytes で stdout へ)。"""
    if args.format == "csv":
        _io.write_csv_stdout(module.render_csv_rows(result))
    elif args.format == "json":
        print(module.render_json(result))
    else:
        print(module.render_text(result))


def _cmd_check_readiness(args: argparse.Namespace) -> int:
    try:
        result = _check_readiness.check(args.business, overlay_paths=args.overlay)
    except (_check_readiness.OverlayError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _check_readiness)
    return _check_readiness.exit_code_for(result)


def _cmd_init(args: argparse.Namespace) -> int:
    import yaml as _yaml

    try:
        if args.format == "csv":
            _io.write_csv_stdout(_init.generate_csv(args.target, overlay_paths=args.overlay))
        else:
            print(_init.generate(args.target, overlay_paths=args.overlay), end="")
    except (
        _check_readiness.OverlayError,
        _patch.InputError,
        FileNotFoundError,
        _yaml.YAMLError,
    ) as e:
        # Missing/broken overlay files follow the CLI-wide input-error
        # contract: [ERROR] + exit 3, never a traceback.
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    return 0


def _cmd_screen_transition(args: argparse.Namespace) -> int:
    try:
        result = _screen.screen(args.task_groups, overlay_paths=args.overlay)
    except (_check_readiness.OverlayError, _screen.InputError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _screen)
    return result.exit_code


def _cmd_score_delegation(args: argparse.Namespace) -> int:
    try:
        result = _score.score(args.judgments, overlay_paths=args.overlay)
    except (_check_readiness.OverlayError, _score.InputError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _score)
    return result.conclusion_exit_code


def _cmd_check_task_contract(args: argparse.Namespace) -> int:
    try:
        result = _task.score(args.contract, overlay_paths=args.overlay)
    except (_check_readiness.OverlayError, _task.InputError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _task)
    return result.exit_code


def _cmd_check_patch_ownership(args: argparse.Namespace) -> int:
    import yaml as _yaml

    try:
        result = _patch.score(args.patch, overlay_paths=args.overlay)
    except (
        _check_readiness.OverlayError,
        _patch.InputError,
        _io.InputFormatError,
        FileNotFoundError,
        _yaml.YAMLError,
    ) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    if args.emit_decision_record:
        try:
            record = _patch.build_decision_record(
                result, team=args.team, overlay_paths=args.overlay
            )
            _patch.append_decision_record(record, args.emit_decision_record)
        except (_patch.InputError, OSError) as e:
            sys.stderr.write(f"[ERROR] {e}\n")
            return 3
    _emit(result, args, _patch)
    return result.exit_code


def _cmd_summarize_patch_decisions(args: argparse.Namespace) -> int:
    import yaml as _yaml

    try:
        result = _decisions.summarize(
            args.decisions,
            period=args.period,
            team=args.team,
            overlay_paths=args.overlay,
        )
    except (
        _decisions.OverlayError,
        _decisions.InputError,
        _io.InputFormatError,
        FileNotFoundError,
        _yaml.YAMLError,
    ) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _decisions)
    return result.exit_code


def _cmd_assess_risk_architecture(args: argparse.Namespace) -> int:
    try:
        result = _risk.assess(args.business, overlay_paths=args.overlay)
    except (_check_readiness.OverlayError, _risk.InputError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _risk)
    return _risk.exit_code_for(result)


def _cmd_validate_audit_log(args: argparse.Namespace) -> int:
    import json as _json

    try:
        result = _validate.validate(args.log, level=args.level)
    except (_json.JSONDecodeError, FileNotFoundError) as e:
        # Malformed/missing input is an input error (exit 3), not an
        # "invalid log" verdict (exit 1) — and never a raw traceback.
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    _emit(result, args, _validate)
    return 0 if result.ok else 1


def _cmd_check_overlay(args: argparse.Namespace) -> int:
    import yaml as _yaml

    try:
        result = _check_overlay.check(args.overlay_path)
    except (FileNotFoundError, _yaml.YAMLError, _io.InputFormatError) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    output = (
        _check_overlay.render_json(result)
        if args.format == "json"
        else _check_overlay.render_text(result)
    )
    print(output)
    return 0 if result.ok else 1


def _cmd_list_definitions(args: argparse.Namespace) -> int:
    import yaml as _yaml

    try:
        summaries = []
        if args.target in {"four-layer", "all"}:
            summaries.append(_list.summarize_four_layer(overlay_paths=args.overlay))
        if args.target in {"matrix", "all"}:
            summaries.append(_list.summarize_matrix(overlay_paths=args.overlay))
        if args.target in {"task-contract", "all"}:
            summaries.append(_list.summarize_task_contract(overlay_paths=args.overlay))
        if args.target in {"transition", "all"}:
            summaries.append(_list.summarize_transition(overlay_paths=args.overlay))
        if args.target in {"patch-ownership", "all"}:
            summaries.append(_list.summarize_patch_ownership(overlay_paths=args.overlay))
        if args.target in {"risk-architecture", "all"}:
            summaries.append(_list.summarize_risk_architecture(overlay_paths=args.overlay))
        if args.target in {"patch-decision", "all"}:
            summaries.append(_list.summarize_patch_decision(overlay_paths=args.overlay))
    except (
        _check_readiness.OverlayError,
        _patch.InputError,
        _risk.InputError,
        _io.InputFormatError,
        _yaml.YAMLError,
    ) as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    except FileNotFoundError as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    if args.format == "json":
        import json
        print(json.dumps([json_loads(s) for s in summaries], indent=2, ensure_ascii=False))
    else:
        for s in summaries:
            print(_list.render_text(s))
            print()
    return 0


def json_loads(summary) -> dict:
    import json
    return json.loads(_list.render_json(summary))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="aidr",
        description=(
            "ai-delegation-readiness CLI. Govern business delegation, "
            "task contracts, audit evidence, and ownership-cost acceptance "
            "of AI-generated patches."
        ),
    )
    parser.add_argument("--version", action="version", version=_version_string())
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser(
        "check-readiness",
        help="Score a business against the 4-layer + efficacy framework",
    )
    p_check.add_argument("business", help="Path to the answers file (CSV or YAML)")
    _shared_overlay_args(p_check, formats=_REPORT_FORMATS)
    p_check.set_defaults(func=_cmd_check_readiness)

    p_init = sub.add_parser(
        "init",
        help="Generate an answer-file template with question comments (write to stdout)",
    )
    p_init.add_argument(
        "--target",
        choices=sorted(_init.TARGETS),
        required=True,
        help="Which input template to generate",
    )
    p_init.add_argument(
        "--overlay",
        action="append",
        default=[],
        metavar="PATH",
        help="Overlay file to include (repeatable; added questions appear in the template)",
    )
    p_init.add_argument(
        "--format",
        choices=["yaml", "csv"],
        default="yaml",
        help="Template format (default: yaml; csv is the spreadsheet-friendly form)",
    )
    p_init.set_defaults(func=_cmd_init)

    p_screen = sub.add_parser(
        "screen-transition",
        help="Screen task groups into the 4 AI-transition types (pre-delegation planning map)",
    )
    p_screen.add_argument("task_groups", help="Path to the task-groups file (CSV or YAML)")
    _shared_overlay_args(p_screen, formats=_REPORT_FORMATS)
    p_screen.set_defaults(func=_cmd_screen_transition)

    p_score = sub.add_parser(
        "score-delegation",
        help="Score per-judgment delegation regions (green/yellow/red)",
    )
    p_score.add_argument("judgments", help="Path to the judgments file (CSV or YAML)")
    _shared_overlay_args(p_score, formats=_REPORT_FORMATS)
    p_score.set_defaults(func=_cmd_score_delegation)

    p_task = sub.add_parser(
        "check-task-contract",
        help="Score a delegated task's execution contract (intent/boundary/evidence/scorer)",
    )
    p_task.add_argument("contract", help="Path to the task-contract file (CSV or YAML)")
    _shared_overlay_args(p_task, formats=_REPORT_FORMATS)
    p_task.set_defaults(func=_cmd_check_task_contract)

    p_patch = sub.add_parser(
        "check-patch-ownership",
        help="Gate an AI-generated patch by ownership cost and acceptance evidence",
    )
    p_patch.add_argument("patch", help="Path to the patch-ownership answers file (CSV or YAML)")
    p_patch.add_argument(
        "--emit-decision-record",
        metavar="PATH",
        help="Append a pending decision record (JSONL) for the later retrospective",
    )
    p_patch.add_argument(
        "--team",
        default="",
        help="Team the patch belongs to (required with --emit-decision-record)",
    )
    _shared_overlay_args(p_patch, formats=_REPORT_FORMATS)
    p_patch.set_defaults(func=_cmd_check_patch_ownership)

    p_dec = sub.add_parser(
        "summarize-patch-decisions",
        help="Report discard rate, decided rate, and discard reasons over recorded decisions",
    )
    p_dec.add_argument("decisions", help="Path to a decision-record JSONL file or a directory")
    p_dec.add_argument("--period", help="Filter to one period (YYYY-MM)")
    p_dec.add_argument("--team", help="Filter to one team")
    _shared_overlay_args(p_dec, formats=_REPORT_FORMATS)
    p_dec.set_defaults(func=_cmd_summarize_patch_decisions)

    p_risk = sub.add_parser(
        "assess-risk-architecture",
        help=(
            "Assess whether the org can detect / contain / escalate agentic "
            "failure scenarios (receiving-side adequacy check)"
        ),
    )
    p_risk.add_argument("business", help="Path to the answers file (CSV or YAML)")
    _shared_overlay_args(p_risk, formats=_REPORT_FORMATS)
    p_risk.set_defaults(func=_cmd_assess_risk_architecture)

    p_val = sub.add_parser(
        "validate-audit-log",
        help="Validate an audit log JSON against the schema",
    )
    p_val.add_argument("log", help="Path to the audit log JSON")
    p_val.add_argument(
        "--level",
        choices=["minimum", "extended"],
        default="minimum",
        help="Schema level: minimum (article-aligned) or extended (J-SOX-grade)",
    )
    p_val.add_argument(
        "--format",
        choices=list(_REPORT_FORMATS),
        default="text",
    )
    p_val.set_defaults(func=_cmd_validate_audit_log)

    p_ov = sub.add_parser(
        "check-overlay",
        help="Validate an overlay's merge rules against the base definition",
    )
    p_ov.add_argument("overlay_path", help="Path to the overlay YAML")
    p_ov.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
    )
    p_ov.set_defaults(func=_cmd_check_overlay)

    p_list = sub.add_parser(
        "list-definitions",
        help="Show base + overlay structure (added questions, strengthened thresholds)",
    )
    p_list.add_argument(
        "--target",
        choices=[
            "four-layer",
            "matrix",
            "task-contract",
            "transition",
            "patch-ownership",
            "patch-decision",
            "risk-architecture",
            "all",
        ],
        default="all",
        help="Which definition(s) to inspect",
    )
    _shared_overlay_args(p_list)
    p_list.set_defaults(func=_cmd_list_definitions)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
