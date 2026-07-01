"""Verify an overlay file against the base definition's merge rules."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import overlay_scoring as overlay_mod

DEFAULT_DEFINITIONS_DIR = Path(__file__).resolve().parents[2] / "definitions"


def _find_base_for(overlay_extends: str, search_dir: Path) -> Path | None:
    for path in search_dir.glob("*.yaml"):
        defn = overlay_mod.load_yaml(path)
        if defn.get("name") == overlay_extends:
            return path
    return None


@dataclass
class OverlayCheck:
    overlay_path: str
    base_path: str | None
    violations: list[overlay_mod.MergeViolation]

    @property
    def ok(self) -> bool:
        return self.base_path is not None and not self.violations


def check(
    overlay_path: str | Path,
    definitions_dir: str | Path | None = None,
) -> OverlayCheck:
    overlay_path = Path(overlay_path)
    definitions_dir = Path(definitions_dir) if definitions_dir else DEFAULT_DEFINITIONS_DIR
    overlay = overlay_mod.load_yaml(overlay_path)
    extends = overlay.get("extends")
    if not extends:
        return OverlayCheck(
            overlay_path=str(overlay_path),
            base_path=None,
            violations=[
                overlay_mod.MergeViolation(
                    path="extends",
                    kind="missing_extends",
                    message="overlay must declare 'extends: <base-definition-name>'",
                )
            ],
        )
    base_path = _find_base_for(extends, definitions_dir)
    if base_path is None:
        return OverlayCheck(
            overlay_path=str(overlay_path),
            base_path=None,
            violations=[
                overlay_mod.MergeViolation(
                    path="extends",
                    kind="unknown_base",
                    message=f"no base definition named '{extends}' found in {definitions_dir}",
                )
            ],
        )
    base = overlay_mod.load_yaml(base_path)
    result = overlay_mod.apply_overlay(base, overlay)
    return OverlayCheck(
        overlay_path=str(overlay_path),
        base_path=str(base_path),
        violations=result.violations,
    )


def render_text(check_result: OverlayCheck) -> str:
    if check_result.ok:
        return (
            f"[OK] overlay {check_result.overlay_path} merges cleanly "
            f"onto base {check_result.base_path}"
        )
    header = f"[NG] overlay {check_result.overlay_path}"
    if check_result.base_path:
        header += f" -> base {check_result.base_path}"
    lines = [header, f"  {len(check_result.violations)} violations:"]
    for v in check_result.violations:
        lines.append(f"  - [{v.kind}] {v.path}: {v.message}")
    return "\n".join(lines)


def render_json(check_result: OverlayCheck) -> str:
    return json.dumps(
        {
            "overlay": check_result.overlay_path,
            "base": check_result.base_path,
            "ok": check_result.ok,
            "violations": [
                {"kind": v.kind, "path": v.path, "message": v.message}
                for v in check_result.violations
            ],
        },
        indent=2,
        ensure_ascii=False,
    )
