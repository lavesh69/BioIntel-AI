from __future__ import annotations

import json
import os
from pathlib import Path

from biointel.tools.runtime import load_manifest, resolve_tool, tool_available, windows_to_wsl_path


def test_advanced_tool_manifest_is_complete():
    manifest = load_manifest()
    tools = manifest["tools"]
    executables = {item["executable"] for item in tools}
    required = {"blastn", "mafft", "hmmscan", "mmseqs", "minimap2", "samtools", "bcftools", "fastqc", "fastp", "multiqc", "bowtie2", "kraken2", "bracken", "metaphlan", "humann", "fastANI", "mash", "prokka", "bakta", "amrfinder", "iqtree3", "vep", "snpEff", "primer3_core", "vina"}
    assert required.issubset(executables)
    assert len(tools) >= 25


def test_application_local_executable_override(tmp_path, monkeypatch):
    home = tmp_path / "tools"
    binary = home / "bin" / ("blastn.exe" if os.name == "nt" else "blastn")
    binary.parent.mkdir(parents=True)
    binary.write_text("fake", encoding="utf-8")
    monkeypatch.setenv("BIOINTEL_TOOLS_HOME", str(home))
    result = resolve_tool("blastn")
    assert result.available
    assert result.backend == "app-local"
    assert tool_available("blastn")


def test_windows_path_conversion():
    assert windows_to_wsl_path(r"C:\Users\Lavesh\sample.fastq.gz") == "/mnt/c/Users/Lavesh/sample.fastq.gz"
    assert windows_to_wsl_path("--threads") == "--threads"
