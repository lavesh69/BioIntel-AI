from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable


_BIOINTEL_IMPORT = re.compile(r"^(?:from\s+biointel\b|import\s+biointel\b)", re.MULTILINE)


@dataclass(frozen=True)
class PageBootstrapAudit:
    page: str
    imports_biointel: bool
    bootstrap_before_import: bool
    production_bootstrap_allowed: bool
    passed: bool


@dataclass(frozen=True)
class PythonCompileResult:
    path: str
    passed: bool
    error: str = ""


def page_entrypoints(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    return [base / "app.py", *sorted((base / "pages").glob("*.py"))]


def audit_page_bootstraps(
    root: str | Path,
    *,
    production_bootstrap_pages: Iterable[str] = (),
) -> list[PageBootstrapAudit]:
    """Audit direct-page import safety without importing the application.

    A Streamlit multipage route can be opened directly by a deep link or desktop
    shortcut. Pages that import ``biointel`` must either insert the project
    ``src`` directory before the first package import or be explicitly covered
    by the production launcher, which exports ``PYTHONPATH=<app>/src``.
    """

    base = Path(root).resolve()
    allowed = {str(value).replace("\\", "/") for value in production_bootstrap_pages}
    rows: list[PageBootstrapAudit] = []
    for page in page_entrypoints(base):
        text = page.read_text(encoding="utf-8", errors="replace")
        match = _BIOINTEL_IMPORT.search(text)
        imports = match is not None
        before = text[: match.start()] if match else text
        self_bootstrap = "sys.path.insert" in before and 'ROOT / "src"' in before
        relative = page.relative_to(base).as_posix()
        production_allowed = relative in allowed
        rows.append(
            PageBootstrapAudit(
                page=relative,
                imports_biointel=imports,
                bootstrap_before_import=(not imports) or self_bootstrap,
                production_bootstrap_allowed=production_allowed,
                passed=(not imports) or self_bootstrap or production_allowed,
            )
        )
    return rows


def compile_python_entrypoints(root: str | Path) -> list[PythonCompileResult]:
    base = Path(root).resolve()
    targets = [
        base / "app.py",
        *sorted((base / "pages").glob("*.py")),
        *sorted((base / "src").rglob("*.py")),
        *sorted((base / "scripts").glob("*.py")),
    ]
    results: list[PythonCompileResult] = []
    for path in targets:
        try:
            source = path.read_text(encoding="utf-8", errors="strict")
            compile(source, str(path), "exec", dont_inherit=True)
        except Exception as exc:  # syntax/import compilation boundary
            results.append(
                PythonCompileResult(
                    path=path.relative_to(base).as_posix(),
                    passed=False,
                    error=f"{type(exc).__name__}: {exc}",
                )
            )
        else:
            results.append(
                PythonCompileResult(path=path.relative_to(base).as_posix(), passed=True)
            )
    return results


def source_connection_audit(root: str | Path) -> dict[str, object]:
    """Detect raw SQLite connections that can leak across Streamlit reruns."""

    base = Path(root).resolve()
    allowed = {
        "src/biointel/database/core.py",
        "src/biointel/engineering/module_reliability.py",
    }
    violations: list[dict[str, object]] = []
    for path in sorted((base / "src").rglob("*.py")):
        relative = path.relative_to(base).as_posix()
        if relative in allowed:
            continue
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8", errors="replace").splitlines(), start=1
        ):
            if "sqlite3.connect(" in line:
                violations.append(
                    {"path": relative, "line": line_number, "source": line.strip()}
                )
    return {
        "passed": not violations,
        "violations": violations,
        "managed_connection_contract": "biointel.database.core.managed_connect",
    }


def runtime_residue(root: str | Path) -> dict[str, object]:
    base = Path(root).resolve()
    residue: list[str] = []
    for path in base.rglob("*"):
        if not path.is_file():
            continue
        name = path.name.lower()
        relative = path.relative_to(base).as_posix()
        if name.endswith((".pyc", "-wal", "-shm")) or "__pycache__" in path.parts:
            residue.append(relative)
        elif name in {".coverage", "coverage.xml"}:
            residue.append(relative)
    return {"passed": not residue, "count": len(residue), "paths": residue}


def reliability_summary(root: str | Path) -> dict[str, object]:
    bootstrap = audit_page_bootstraps(
        root,
        production_bootstrap_pages={"pages/157_Instrument_Integration_Hub_2.py"},
    )
    compile_rows = compile_python_entrypoints(root)
    connection = source_connection_audit(root)
    return {
        "schema": "biointel.module-reliability.v1",
        "page_entrypoints": len(bootstrap),
        "page_bootstrap_passed": sum(item.passed for item in bootstrap),
        "page_bootstrap_failures": [asdict(item) for item in bootstrap if not item.passed],
        "python_files": len(compile_rows),
        "python_compile_passed": sum(item.passed for item in compile_rows),
        "python_compile_failures": [asdict(item) for item in compile_rows if not item.passed],
        "sqlite_connection_audit": connection,
        "passed": all(item.passed for item in bootstrap)
        and all(item.passed for item in compile_rows)
        and bool(connection["passed"]),
    }
