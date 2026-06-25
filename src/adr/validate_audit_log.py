"""Validate an audit log JSON against ``schemas/audit-log.schema.json``.

The schema has two levels (in ``$defs``):

- ``audit_log_minimum``  : article-aligned baseline (A)
- ``audit_log_extended`` : J-SOX-grade design additions (B)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

DEFAULT_SCHEMA = Path(__file__).resolve().parents[2] / "schemas" / "audit-log.schema.json"


@dataclass
class Violation:
    path: str
    message: str


@dataclass
class ValidationResult:
    level: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def _build_validator(schema_path: Path, level: str) -> Draft202012Validator:
    schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
    schema_id = schema.get("$id", str(schema_path))
    resource = Resource.from_contents(schema, default_specification=DRAFT202012)
    registry: Registry = Registry().with_resource(schema_id, resource)
    sub_schema = {"$ref": f"{schema_id}#/$defs/{level}"}
    # format_checker を渡さないと "format": "date-time" 等は no-op になり、
    # "when": "not-a-date" のような無効値が通ってしまう。監査ログの時刻保証として
    # 致命的なので必ず有効化する。
    return Draft202012Validator(
        sub_schema,
        registry=registry,
        format_checker=Draft202012Validator.FORMAT_CHECKER,
    )


def validate(
    log_path: str | Path,
    level: str = "minimum",
    schema_path: str | Path | None = None,
) -> ValidationResult:
    schema_path = Path(schema_path) if schema_path else DEFAULT_SCHEMA
    if level not in {"minimum", "extended"}:
        raise ValueError(f"unknown level: {level}; expected 'minimum' or 'extended'")
    validator = _build_validator(schema_path, f"audit_log_{level}")
    data = json.loads(Path(log_path).read_text(encoding="utf-8"))

    violations: list[Violation] = []
    for err in validator.iter_errors(data):
        path = "/" + "/".join(str(p) for p in err.absolute_path)
        violations.append(Violation(path=path, message=err.message))
    return ValidationResult(level=level, violations=violations)


def render_text(result: ValidationResult) -> str:
    if result.ok:
        return f"[OK] schema=audit_log_{result.level}: valid"
    lines = [f"[NG] schema=audit_log_{result.level}: {len(result.violations)} violations"]
    for v in result.violations:
        lines.append(f"  - {v.path}: {v.message}")
    return "\n".join(lines)


def render_json(result: ValidationResult) -> str:
    return json.dumps(
        {
            "level": result.level,
            "ok": result.ok,
            "violations": [{"path": v.path, "message": v.message} for v in result.violations],
        },
        indent=2,
        ensure_ascii=False,
    )
