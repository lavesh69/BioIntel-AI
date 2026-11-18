from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class EngineeringGateResult:
    name: str
    passed: bool
    evidence: str


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}


def verify_exact_lock(root: Path) -> EngineeringGateResult:
    lock = root / "requirements.lock"
    lines = [line.strip() for line in lock.read_text(encoding="utf-8").splitlines() if line.strip() and not line.startswith("#")]
    invalid = [line for line in lines if "==" not in line or line.startswith(("-r", "--"))]
    digest_file = root / "requirements.lock.sha256"
    observed = hashlib.sha256(lock.read_bytes()).hexdigest()
    expected = digest_file.read_text(encoding="utf-8").strip().split()[0] if digest_file.exists() else ""
    return EngineeringGateResult("exact_dependency_lock", not invalid and observed == expected, f"packages={len(lines)} invalid={len(invalid)} sha256={observed}")


def check_architecture(root: Path) -> EngineeringGateResult:
    policy = _load_yaml(root / "config/architecture_rules.yaml")
    forbidden = {item["from"]: tuple(item["cannot_import"]) for item in policy.get("forbidden_imports", [])}
    violations: list[str] = []
    source = root / "src/biointel"
    for path in source.rglob("*.py"):
        module = ".".join(path.relative_to(root / "src").with_suffix("").parts)
        try:
            tree = ast.parse(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, SyntaxError) as exc:
            violations.append(f"{path}:{getattr(exc, 'lineno', 1)}:syntax")
            continue
        imports: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        for prefix, denied in forbidden.items():
            if module.startswith(prefix):
                for imported in imports:
                    if any(imported.startswith(target) for target in denied):
                        violations.append(f"{module}->{imported}")
    return EngineeringGateResult("architecture_boundaries", not violations, "violations=" + (", ".join(violations[:10]) or "0"))


def check_technical_debt(root: Path) -> EngineeringGateResult:
    data = _load_yaml(root / "TECHNICAL_DEBT.yaml")
    today = date.today()
    overdue = []
    for item in data.get("items", []):
        due = date.fromisoformat(str(item["due_date"]))
        if item.get("status") not in {"closed", "accepted"} and due < today:
            overdue.append(item.get("id", "unknown"))
    return EngineeringGateResult("technical_debt_expiry", not overdue, "overdue=" + (", ".join(overdue) or "0"))


def check_quality_budgets(root: Path) -> EngineeringGateResult:
    budgets = _load_yaml(root / "config/quality_budgets.yaml")
    max_lines = int(budgets["python"]["max_module_lines"])
    exclusions = tuple(budgets["python"].get("legacy_exclusions", []))
    offenders = []
    for path in (root / "src/biointel").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        if rel in exclusions:
            continue
        lines = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        if lines > max_lines:
            offenders.append(f"{rel}:{lines}")
    return EngineeringGateResult("module_size_budget", not offenders, "offenders=" + (", ".join(offenders[:10]) or "0"))


def run_engineering_gates(root: str | Path) -> dict[str, Any]:
    base = Path(root).resolve()
    results = [verify_exact_lock(base), check_architecture(base), check_technical_debt(base), check_quality_budgets(base)]
    return {
        "schema": "biointel.engineering-gates.v1",
        "passed": all(item.passed for item in results),
        "results": [asdict(item) for item in results],
    }


def write_gate_report(root: str | Path, output: str | Path) -> Path:
    target = Path(output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(run_engineering_gates(root), indent=2, sort_keys=True), encoding="utf-8")
    return target
