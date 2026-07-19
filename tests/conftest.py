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


def task_contract_path() -> Path:
    return DEFINITIONS_DIR / "task-contract.yaml"


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


def hs_overlay_four_layer_path() -> Path:
    return EXAMPLES_DIR / "overlays" / "high-stakes-domain" / "four-layer.yaml"


def hs_overlay_matrix_path() -> Path:
    return EXAMPLES_DIR / "overlays" / "high-stakes-domain" / "delegation-matrix.yaml"


def sample_ip_business_path() -> Path:
    return EXAMPLES_DIR / "business" / "sample-ip-agent-readiness.yaml"


def sample_ip_judgments_path() -> Path:
    return EXAMPLES_DIR / "judgments" / "sample-ip-judgments.yaml"


def insourcing_overlay_path() -> Path:
    return EXAMPLES_DIR / "overlays" / "insourcing-judgment" / "four-layer.yaml"


def sample_insourcing_business_path() -> Path:
    return EXAMPLES_DIR / "business" / "sample-insourcing-readiness.yaml"


def transition_path() -> Path:
    return DEFINITIONS_DIR / "transition-screening.yaml"


def sample_task_groups_path() -> Path:
    return EXAMPLES_DIR / "task-groups" / "sample-task-groups.yaml"


def sample_task_contract_green_path() -> Path:
    return EXAMPLES_DIR / "task-contracts" / "sample-green.yaml"


def sample_task_contract_red_path() -> Path:
    return EXAMPLES_DIR / "task-contracts" / "sample-red-ai-judge.yaml"
