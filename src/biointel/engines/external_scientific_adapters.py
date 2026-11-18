"""
BioIntel AI 15.6.0 — External Scientific Engine Execution & Adapter Framework
Provides executable path detection, version checking, structured process arguments,
timeout handling, stdout/stderr capture, result validation, and diagnostic fallback states.
"""

import os
import sys
import shutil
import subprocess
import logging
import json
import time
from typing import Dict, Any, List, Optional, Tuple

logger = logging.getLogger("biointel.engines.external_adapters")

# Honest Status Constants
STATUS_READY = "Ready"
STATUS_NOT_CONFIGURED = "Not Configured"
STATUS_ENGINE_MISSING = "External Engine Missing"
STATUS_RUNNING = "Running"
STATUS_COMPLETED = "Completed"
STATUS_COMPLETED_WARNINGS = "Completed With Warnings"
STATUS_FAILED = "Failed"
STATUS_DEMO_MODE = "Demo Mode"


class ExternalScientificEngineAdapter:
    """Universal adapter framework for detecting, configuring, and executing external scientific tools."""

    SUPPORTED_ENGINES = {
        "FSL": {"execs": ["fsl", "fslmaths", "flirt", "bet"], "os": ["linux", "darwin", "wsl2"]},
        "FreeSurfer": {"execs": ["recon-all", "mri_convert"], "os": ["linux", "darwin", "wsl2"]},
        "ANTs": {"execs": ["antsRegistration", "antsApplyTransforms"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "AFNI": {"execs": ["afni", "3dvolreg"], "os": ["linux", "darwin", "wsl2"]},
        "MRtrix3": {"execs": ["mrconvert", "dwifslpreproc"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "BWA": {"execs": ["bwa", "bwa-mem2"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "Bowtie2": {"execs": ["bowtie2"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "Minimap2": {"execs": ["minimap2"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "SAMtools": {"execs": ["samtools"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "BCFtools": {"execs": ["bcftools"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "BEDTools": {"execs": ["bedtools"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "FastQC": {"execs": ["fastqc"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "MultiQC": {"execs": ["multiqc"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "VEP": {"execs": ["vep"], "os": ["linux", "darwin", "wsl2"]},
        "SnpEff": {"execs": ["snpEff"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "PLINK2": {"execs": ["plink2", "plink"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "Kraken2": {"execs": ["kraken2"], "os": ["linux", "darwin", "wsl2"]},
        "HUMAnN": {"execs": ["humann"], "os": ["linux", "darwin", "wsl2"]},
        "GROMACS": {"execs": ["gmx"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "OpenMM": {"execs": ["python"], "python_module": "openmm", "os": ["linux", "darwin", "wsl2", "windows"]},
        "AutoDock Vina": {"execs": ["vina", "vina.exe"], "os": ["linux", "darwin", "wsl2", "windows"]},
        "Cellpose": {"execs": ["cellpose", "python"], "python_module": "cellpose", "os": ["linux", "darwin", "wsl2", "windows"]},
        "StarDist": {"execs": ["python"], "python_module": "stardist", "os": ["linux", "darwin", "wsl2", "windows"]},
        "OpenSlide": {"execs": ["python"], "python_module": "openslide", "os": ["linux", "darwin", "wsl2", "windows"]},
        "RFdiffusion": {"execs": ["python"], "python_module": "rfdiffusion", "os": ["linux", "darwin", "wsl2"]},
        "ProteinMPNN": {"execs": ["python"], "python_module": "proteinmpnn", "os": ["linux", "darwin", "wsl2", "windows"]},
        "MSConvert": {"execs": ["msconvert", "msconvert.exe"], "os": ["windows", "wsl2"]},
    }

    def __init__(self):
        self.detected_cache = {}

    def detect_engine(self, engine_name: str) -> Dict[str, Any]:
        """Detect executable path, version, and availability for a target engine."""
        if engine_name not in self.SUPPORTED_ENGINES:
            return {
                "name": engine_name,
                "status": STATUS_NOT_CONFIGURED,
                "available": False,
                "error": f"Unknown scientific engine '{engine_name}'",
            }

        info = self.SUPPORTED_ENGINES[engine_name]
        py_module = info.get("python_module")

        # Check Python module if specified
        if py_module:
            try:
                mod = __import__(py_module)
                version = getattr(mod, "__version__", "Available")
                return {
                    "name": engine_name,
                    "status": STATUS_READY,
                    "available": True,
                    "type": "Python Module",
                    "module_name": py_module,
                    "version": str(version),
                    "path": getattr(mod, "__file__", "Python Site-Packages"),
                }
            except ImportError:
                pass

        # Check binary executable on PATH
        for ex in info["execs"]:
            path = shutil.which(ex)
            if path:
                version = self._get_binary_version(path)
                return {
                    "name": engine_name,
                    "status": STATUS_READY,
                    "available": True,
                    "type": "Native Executable",
                    "executable": ex,
                    "path": path,
                    "version": version,
                }

        # Check WSL2 fallback if on Windows
        wsl2_available = False
        if sys.platform == "win32":
            wsl2_path = shutil.which("wsl")
            if wsl2_path:
                wsl2_available = True

        return {
            "name": engine_name,
            "status": STATUS_ENGINE_MISSING,
            "available": False,
            "installation_instructions": f"Install {engine_name} natively or in WSL2/Conda.",
            "supported_os": info["os"],
            "wsl2_fallback_capable": wsl2_available,
        }

    def _get_binary_version(self, path: str) -> str:
        """Safely fetch version string from binary."""
        try:
            res = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=3)
            out = (res.stdout or res.stderr or "").strip().split("\n")[0]
            return out[:60] if out else "Detected"
        except Exception:
            return "Detected"

    def execute_engine(
        self,
        engine_name: str,
        args: List[str],
        expected_outputs: Optional[List[str]] = None,
        timeout_seconds: int = 300,
    ) -> Dict[str, Any]:
        """Execute an external engine process safely with structured arguments and verification."""
        det = self.detect_engine(engine_name)
        provenance = {
            "engine": engine_name,
            "timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "arguments": args,
        }

        if not det["available"]:
            return {
                "status": STATUS_ENGINE_MISSING,
                "engine_detection": det,
                "error": f"External engine '{engine_name}' is not installed or available on PATH.",
                "provenance": provenance,
            }

        exe_path = det.get("path")
        cmd = [exe_path] + args if det.get("type") == "Native Executable" else [sys.executable, "-m", det.get("module_name", "")] + args

        start_t = time.time()
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_seconds)
            elapsed = time.time() - start_t

            # Verify return code
            if res.returncode != 0:
                return {
                    "status": STATUS_FAILED,
                    "returncode": res.returncode,
                    "stdout": res.stdout[:2000],
                    "stderr": res.stderr[:2000],
                    "elapsed_seconds": round(elapsed, 2),
                    "provenance": provenance,
                }

            # Verify expected output files
            missing_outputs = []
            if expected_outputs:
                for out_f in expected_outputs:
                    if not os.path.exists(out_f) or os.path.getsize(out_f) == 0:
                        missing_outputs.append(out_f)

            if missing_outputs:
                return {
                    "status": STATUS_COMPLETED_WARNINGS,
                    "warning": f"Execution completed with exit code 0, but output files are missing or 0 bytes: {missing_outputs}",
                    "stdout": res.stdout[:2000],
                    "stderr": res.stderr[:2000],
                    "elapsed_seconds": round(elapsed, 2),
                    "provenance": provenance,
                }

            return {
                "status": STATUS_COMPLETED,
                "returncode": 0,
                "stdout": res.stdout[:2000],
                "elapsed_seconds": round(elapsed, 2),
                "expected_outputs_verified": expected_outputs or [],
                "provenance": provenance,
            }

        except subprocess.TimeoutExpired:
            return {
                "status": STATUS_FAILED,
                "error": f"Engine execution timed out after {timeout_seconds} seconds.",
                "provenance": provenance,
            }
        except Exception as e:
            return {
                "status": STATUS_FAILED,
                "error": f"Process execution error: {str(e)}",
                "provenance": provenance,
            }


if __name__ == "__main__":
    adapter = ExternalScientificEngineAdapter()
    print("Engine Detection Probes:")
    for eng in ["BWA", "OpenMM", "SAMtools", "FSL", "AutoDock Vina", "Cellpose"]:
        res = adapter.detect_engine(eng)
        print(f"  [{eng}] Available: {res['available']} | Status: {res['status']}")
