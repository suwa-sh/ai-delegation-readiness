"""Command-line entry point for ``aidr``.

Subcommands:
    check-readiness        4-layer + efficacy readiness check
    score-delegation       delegation matrix scoring per judgment
    validate-audit-log     JSON Schema validation (minimum or extended)
    check-overlay          overlay merge-rule validation
    list-definitions       inspect loaded base + overlay structure
"""

from __future__ import annotations

import argparse
import sys
from importlib.metadata import PackageNotFoundError, version as _pkg_version
from pathlib import Path

import overlay_scoring

from . import (
    check_overlay as _check_overlay,
    check_readiness as _check_readiness,
    list_definitions as _list,
    score_delegation as _score,
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


def _shared_overlay_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--overlay",
        action="append",
        default=[],
        metavar="PATH",
        help="Overlay file to apply (repeatable; applied in order)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="Output format (default: text)",
    )


def _cmd_check_readiness(args: argparse.Namespace) -> int:
    try:
        result = _check_readiness.check(args.business, overlay_paths=args.overlay)
    except _check_readiness.OverlayError as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    output = (
        _check_readiness.render_json(result)
        if args.format == "json"
        else _check_readiness.render_text(result)
    )
    print(output)
    return _check_readiness.exit_code_for(result)


def _cmd_score_delegation(args: argparse.Namespace) -> int:
    try:
        result = _score.score(args.judgments, overlay_paths=args.overlay)
    except _check_readiness.OverlayError as e:
        sys.stderr.write(f"[ERROR] {e}\n")
        return 3
    output = (
        _score.render_json(result)
        if args.format == "json"
        else _score.render_text(result)
    )
    print(output)
    return result.conclusion_exit_code


def _cmd_validate_audit_log(args: argparse.Namespace) -> int:
    result = _validate.validate(args.log, level=args.level)
    output = (
        _validate.render_json(result)
        if args.format == "json"
        else _validate.render_text(result)
    )
    print(output)
    return 0 if result.ok else 1


def _cmd_check_overlay(args: argparse.Namespace) -> int:
    result = _check_overlay.check(args.overlay_path)
    output = (
        _check_overlay.render_json(result)
        if args.format == "json"
        else _check_overlay.render_text(result)
    )
    print(output)
    return 0 if result.ok else 1


def _cmd_list_definitions(args: argparse.Namespace) -> int:
    try:
        summaries = []
        if args.target in {"four-layer", "all"}:
            summaries.append(_list.summarize_four_layer(overlay_paths=args.overlay))
        if args.target in {"matrix", "all"}:
            summaries.append(_list.summarize_matrix(overlay_paths=args.overlay))
    except _check_readiness.OverlayError as e:
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
            "ai-delegation-readiness CLI. Diagnose whether a business "
            "judgment is ready to be delegated to an AI agent, and "
            "validate the audit log it produces."
        ),
    )
    parser.add_argument("--version", action="version", version=_version_string())
    sub = parser.add_subparsers(dest="command", required=True)

    p_check = sub.add_parser(
        "check-readiness",
        help="Score a business against the 4-layer + efficacy framework",
    )
    p_check.add_argument("business", help="Path to the business answers YAML")
    _shared_overlay_args(p_check)
    p_check.set_defaults(func=_cmd_check_readiness)

    p_score = sub.add_parser(
        "score-delegation",
        help="Score per-judgment delegation regions (green/yellow/red)",
    )
    p_score.add_argument("judgments", help="Path to the judgments YAML")
    _shared_overlay_args(p_score)
    p_score.set_defaults(func=_cmd_score_delegation)

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
        choices=["text", "json"],
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
        choices=["four-layer", "matrix", "all"],
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
