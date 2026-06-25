"""Shared pytest fixtures and path setup."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"
DEFINITIONS_DIR = REPO_ROOT / "definitions"
SCHEMAS_DIR = REPO_ROOT / "schemas"
EXAMPLES_DIR = REPO_ROOT / "examples"

# Make src/ importable for plain `pytest` runs
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))


def four_layer_path() -> Path:
    return DEFINITIONS_DIR / "four-layer.yaml"


def matrix_path() -> Path:
    return DEFINITIONS_DIR / "delegation-matrix.yaml"


def audit_schema_path() -> Path:
    return SCHEMAS_DIR / "audit-log.schema.json"


def sample_audit_log_path() -> Path:
    return EXAMPLES_DIR / "audit-log-sample.json"


def sample_business_path() -> Path:
    return EXAMPLES_DIR / "business" / "sample-expense-approval.yaml"


def sample_judgments_path() -> Path:
    return EXAMPLES_DIR / "judgments" / "sample-judgments.yaml"


def sample_overlay_path() -> Path:
    return EXAMPLES_DIR / "overlays" / "sample-company" / "extra-rules.yaml"
