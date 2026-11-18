from __future__ import annotations

import tempfile
from pathlib import Path
from biointel.tools.runtime import run_tool, tool_available


def run_command(
    arguments: list[str], *, timeout_seconds: int = 300, cwd: str | Path | None = None
) -> dict:
    if not arguments:
        raise ValueError("Command arguments are required.")
    if not tool_available(arguments[0]):
        raise RuntimeError(f"{arguments[0]} is not installed. Run INSTALL_ADVANCED_TOOLS_WINDOWS.bat.")
    completed = run_tool(
        arguments[0], arguments[1:], cwd=cwd, timeout_seconds=timeout_seconds, check=False
    )
    if completed.returncode:
        raise RuntimeError((completed.stderr or completed.stdout or "Command failed").strip())
    return {
        "return_code": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }


def run_mafft(fasta_text: str, *, timeout_seconds: int = 300) -> str:
    with tempfile.TemporaryDirectory(prefix="biointel_mafft_") as tmp:
        path = Path(tmp) / "input.fasta"
        path.write_text(fasta_text, encoding="utf-8")
        return run_command(
            ["mafft", "--auto", "--quiet", str(path)], timeout_seconds=timeout_seconds
        )["stdout"]


def run_blastn(
    query_fasta: str, database: str, *, max_targets: int = 25, timeout_seconds: int = 300
) -> str:
    with tempfile.TemporaryDirectory(prefix="biointel_blast_") as tmp:
        path = Path(tmp) / "query.fasta"
        path.write_text(query_fasta, encoding="utf-8")
        return run_command(
            [
                "blastn",
                "-query",
                str(path),
                "-db",
                database,
                "-outfmt",
                "6",
                "-max_target_seqs",
                str(max_targets),
            ],
            timeout_seconds=timeout_seconds,
        )["stdout"]


def run_hmmscan(sequence_fasta: str, hmm_database: str, *, timeout_seconds: int = 300) -> str:
    with tempfile.TemporaryDirectory(prefix="biointel_hmmer_") as tmp:
        query = Path(tmp) / "query.fasta"
        table = Path(tmp) / "hits.tbl"
        query.write_text(sequence_fasta, encoding="utf-8")
        run_command(
            ["hmmscan", "--noali", "--tblout", str(table), hmm_database, str(query)],
            timeout_seconds=timeout_seconds,
        )
        return table.read_text(encoding="utf-8", errors="replace")
