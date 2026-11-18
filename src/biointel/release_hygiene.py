from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
import shutil


RUNTIME_FILE_SUFFIXES = ("-wal", "-shm", ".pyc", ".pyo")
RUNTIME_DIRECTORY_NAMES = {"__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache"}


@dataclass(frozen=True)
class HygieneReport:
    root: str
    removed_files: tuple[str, ...]
    removed_directories: tuple[str, ...]
    failures: tuple[str, ...]

    @property
    def clean(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict[str, object]:
        return {**asdict(self), "clean": self.clean}


def is_runtime_residue(path: Path) -> bool:
    return path.name in RUNTIME_DIRECTORY_NAMES or path.name.endswith(RUNTIME_FILE_SUFFIXES)


def audit_runtime_residue(root: str | Path) -> list[Path]:
    base = Path(root).resolve()
    if not base.exists():
        return []
    return sorted((path for path in base.rglob("*") if is_runtime_residue(path)), key=lambda item: (len(item.parts), str(item)), reverse=True)


def clean_runtime_residue(root: str | Path) -> HygieneReport:
    base = Path(root).resolve()
    removed_files: list[str] = []
    removed_directories: list[str] = []
    failures: list[str] = []
    for path in audit_runtime_residue(base):
        try:
            relative = str(path.relative_to(base))
            if path.is_dir():
                shutil.rmtree(path)
                removed_directories.append(relative)
            elif path.exists():
                path.unlink()
                removed_files.append(relative)
        except OSError as exc:
            failures.append(f"{path}: {type(exc).__name__}: {exc}")
    return HygieneReport(str(base), tuple(sorted(removed_files)), tuple(sorted(removed_directories)), tuple(failures))


__all__ = [
    "HygieneReport",
    "RUNTIME_DIRECTORY_NAMES",
    "RUNTIME_FILE_SUFFIXES",
    "audit_runtime_residue",
    "clean_runtime_residue",
    "is_runtime_residue",
]
