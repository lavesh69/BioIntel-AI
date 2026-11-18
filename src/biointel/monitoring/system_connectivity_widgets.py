"""Bounded real connectivity, provider, process and infrastructure probes."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import tempfile
import time
from typing import Any, Callable
import urllib.error
import urllib.request

STATUS_ONLINE = "Online"
STATUS_OFFLINE = "Offline"
STATUS_LIMITED = "Limited Connectivity"
STATUS_MOCK_MODE = "Mock Mode"
STATUS_GPU_UNAVAILABLE = "GPU Unavailable"
STATUS_WSL_UNAVAILABLE = "WSL2 Unavailable"
STATUS_DOCKER_UNAVAILABLE = "Docker Unavailable"

PUBLIC_CONNECTORS = {
    "PubMed / NCBI": "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/einfo.fcgi?retmode=json",
    "Crossref DOI": "https://api.crossref.org/works?rows=0",
    "ClinicalTrials.gov": "https://clinicaltrials.gov/api/v2/studies?pageSize=1",
    "UniProt Knowledgebase": "https://rest.uniprot.org/uniprotkb/search?query=*&size=1&format=json",
    "Ensembl Genomics": "https://rest.ensembl.org/info/ping?content-type=application/json",
    "Hugging Face Model Hub": "https://huggingface.co/api/models?limit=1",
    "OpenAlex": "https://api.openalex.org/works?per-page=1",
    "Open-Meteo Weather": "https://api.open-meteo.com/v1/forecast?latitude=0&longitude=0&current=temperature_2m",
    "Open-Meteo Air Quality": "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=0&longitude=0&current=us_aqi",
}
CONFIGURED_CONNECTORS = {
    "FHIR R4 Clinical API": "BIOINTEL_FHIR_URL",
    "DICOMweb PACS Server": "BIOINTEL_DICOMWEB_URL",
    "REDCap Clinical EDC": "BIOINTEL_REDCAP_URL",
    "LIMS Instrument Gateway": "BIOINTEL_LIMS_URL",
}


def _utc() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class SystemConnectivityWidgetsEngine:
    def __init__(self, *, opener: Callable[..., Any] | None = None, timeout: float = 3.0) -> None:
        self._opener = opener or urllib.request.urlopen
        self.timeout = max(0.5, timeout)
        self._history: dict[str, dict[str, str | None]] = {}

    def _probe_url(self, name: str, url: str | None) -> dict[str, Any]:
        if not url:
            return {"status": "Not Configured", "mode": "Configuration Required", "latency_ms": None,
                "http_status": None, "authentication_state": "Not Configured", "rate_limit_state": "Unknown",
                "last_success": None, "last_failure": None, "safe_error": "Endpoint is not configured.",
                "cache_fallback": False, "endpoint": None}
        if not url.lower().startswith("https://"):
            return {"status": "Configuration Error", "mode": "TLS Required", "latency_ms": None,
                "http_status": None, "authentication_state": "Unknown", "rate_limit_state": "Unknown",
                "last_success": None, "last_failure": _utc(), "safe_error": "Only HTTPS endpoints are allowed.",
                "cache_fallback": False, "endpoint": url}
        started = time.perf_counter()
        request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "BioIntelAI/15.6.0"})
        status, code, error, auth, rate = STATUS_OFFLINE, None, "", "Not Required or Unknown", "Unknown"
        headers: Any = {}
        try:
            with self._opener(request, timeout=self.timeout) as response:
                code = int(getattr(response, "status", 200))
                headers = getattr(response, "headers", {})
                response.read(512)
                if code == 429:
                    status, rate = "Rate Limited", "Rate Limited"
                elif code in (401, 403):
                    status, auth = "Authentication Required", "Authentication Required"
                elif 200 <= code < 400:
                    status = STATUS_ONLINE
                else:
                    status, error = "Provider Unavailable", f"HTTP {code}"
        except urllib.error.HTTPError as exc:
            code = exc.code
            if code == 429:
                status, rate = "Rate Limited", "Rate Limited"
            elif code in (401, 403):
                status, auth = "Authentication Required", "Authentication Required"
            else:
                status, error = "Provider Unavailable", f"HTTP {code}"
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            error = f"{type(exc).__name__}: connection failed"
        latency = round((time.perf_counter() - started) * 1000, 1)
        now = _utc()
        history = self._history.setdefault(name, {"last_success": None, "last_failure": None})
        history["last_success" if status == STATUS_ONLINE else "last_failure"] = now
        remaining = headers.get("X-RateLimit-Remaining") if hasattr(headers, "get") else None
        reset = headers.get("X-RateLimit-Reset") if hasattr(headers, "get") else None
        if remaining is not None:
            rate = f"Remaining {remaining}" + (f"; reset {reset}" if reset else "")
        return {"status": status, "mode": "Live HTTPS Probe", "latency_ms": latency,
            "http_status": code, "authentication_state": auth, "rate_limit_state": rate,
            "last_success": history["last_success"], "last_failure": history["last_failure"],
            "safe_error": error, "cache_fallback": False, "endpoint": url}

    def check_internet_status(self, mode: str = "Auto Detect") -> dict[str, Any]:
        provenance = {"widget": "Internet Status Widget", "mode": mode, "timestamp_utc": _utc()}
        if mode in {"Air-Gapped", "Offline"}:
            return {"status": STATUS_OFFLINE, "mode": mode, "latency_ms": None,
                "dns_status": "Disabled by selected mode", "https_status": "Disabled",
                "last_success": None, "provenance": provenance}
        dns_started = time.perf_counter()
        try:
            socket.getaddrinfo("clinicaltrials.gov", 443, type=socket.SOCK_STREAM)
            dns_status = "Resolved"
        except OSError:
            dns_status = "DNS Unreachable"
        probe = self._probe_url("Internet HTTPS probe", "https://clinicaltrials.gov/api/v2/studies?pageSize=1")
        online = dns_status == "Resolved" and probe["status"] in {STATUS_ONLINE, "Authentication Required"}
        status = STATUS_ONLINE if online else STATUS_LIMITED if dns_status == "Resolved" else STATUS_OFFLINE
        return {"status": status, "mode": mode, "latency_ms": probe["latency_ms"],
            "dns_latency_ms": round((time.perf_counter() - dns_started) * 1000, 1),
            "dns_status": dns_status, "https_status": probe["status"],
            "http_status": probe["http_status"], "safe_error": probe["safe_error"],
            "last_success": probe["last_success"], "provenance": provenance}

    def get_api_health_matrix(self) -> dict[str, Any]:
        targets = dict(PUBLIC_CONNECTORS)
        targets.update({name: os.environ.get(variable, "").strip() or None for name, variable in CONFIGURED_CONNECTORS.items()})
        connectors: dict[str, dict[str, Any]] = {}
        with ThreadPoolExecutor(max_workers=6, thread_name_prefix="biointel-health") as pool:
            futures = {pool.submit(self._probe_url, name, url): name for name, url in targets.items()}
            for future in as_completed(futures):
                name = futures[future]
                try:
                    connectors[name] = future.result()
                except Exception as exc:
                    connectors[name] = {"status": "Probe Failed", "mode": "Live HTTPS Probe",
                        "latency_ms": None, "http_status": None, "authentication_state": "Unknown",
                        "rate_limit_state": "Unknown", "last_success": None, "last_failure": _utc(),
                        "safe_error": type(exc).__name__, "cache_fallback": False, "endpoint": targets[name]}
        ordered = {name: connectors[name] for name in targets}
        return {"status": "Measured", "total_connectors": len(ordered),
            "online_count": sum(value["status"] == STATUS_ONLINE for value in ordered.values()),
            "not_configured_count": sum(value["status"] == "Not Configured" for value in ordered.values()),
            "connectors": ordered, "timestamp_utc": _utc()}

    def inspect_tls_and_proxy(self) -> dict[str, Any]:
        http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
        https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
        ca_bundle = os.environ.get("SSL_CERT_FILE") or os.environ.get("REQUESTS_CA_BUNDLE")
        try:
            ssl.create_default_context(cafile=ca_bundle or None)
            tls_context = "Default TLS context created"
        except (OSError, ssl.SSLError) as exc:
            tls_context = f"TLS context error: {type(exc).__name__}"
        return {"status": "Inspected", "system_proxy_detected": bool(http_proxy or https_proxy),
            "http_proxy": "Configured" if http_proxy else "Direct / not declared",
            "https_proxy": "Configured" if https_proxy else "Direct / not declared",
            "custom_ca_configured": bool(ca_bundle), "ssl_verification_active": True,
            "certificate_chain_valid": "Not tested against a specific endpoint", "tls_context": tls_context,
            "provenance": {"widget": "Proxy & TLS Inspector", "timestamp_utc": _utc()}}

    @staticmethod
    def _run(arguments: list[str], timeout: float = 4.0) -> dict[str, Any]:
        try:
            completed = subprocess.run(arguments, capture_output=True, text=True, timeout=timeout, check=False,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            return {"exit_code": completed.returncode, "stdout": completed.stdout.strip()[:2000],
                "stderr": completed.stderr.strip()[:1000], "timed_out": False}
        except subprocess.TimeoutExpired:
            return {"exit_code": None, "stdout": "", "stderr": "Timed out", "timed_out": True}
        except OSError as exc:
            return {"exit_code": None, "stdout": "", "stderr": type(exc).__name__, "timed_out": False}

    def check_gpu_telemetry(self) -> dict[str, Any]:
        provenance = {"widget": "GPU Runtime Widget", "timestamp_utc": _utc()}
        executable = shutil.which("nvidia-smi")
        if executable:
            result = self._run([executable, "--query-gpu=name,driver_version,memory.total,memory.used", "--format=csv,noheader,nounits"])
            if result["exit_code"] == 0 and result["stdout"]:
                name, driver, total, used = [value.strip() for value in result["stdout"].splitlines()[0].split(",")[:4]]
                return {"status": STATUS_ONLINE, "gpu_detected": True, "gpu_name": name,
                    "driver_version": driver, "vram_total_mb": _safe_float(total),
                    "vram_allocated_mb": _safe_float(used),
                    "vram_available_mb": _safe_float(total) - _safe_float(used),
                    "cuda_version": "Not queried", "framework_availability": "Not tested",
                    "active_biointel_workload": "Not determined", "execution_device": "GPU available", "provenance": provenance}
        return {"status": STATUS_GPU_UNAVAILABLE, "gpu_detected": False, "execution_device": "CPU fallback",
            "note": "No qualified NVIDIA telemetry was returned.", "provenance": provenance}

    def inspect_docker_wsl2_status(self) -> dict[str, Any]:
        wsl, docker = shutil.which("wsl.exe") or shutil.which("wsl"), shutil.which("docker.exe") or shutil.which("docker")
        wsl_result = self._run([wsl, "--list", "--verbose"]) if wsl else None
        docker_result = self._run([docker, "version", "--format", "{{json .Server}}"] ) if docker else None
        return {"status": "Inspected", "wsl2": {"installed": bool(wsl),
            "status": "Ready" if wsl_result and wsl_result["exit_code"] == 0 else STATUS_WSL_UNAVAILABLE,
            "executable": wsl or "Not Found", "distributions": wsl_result["stdout"] if wsl_result else "Not tested"},
            "docker": {"installed": bool(docker),
            "daemon_running": bool(docker_result and docker_result["exit_code"] == 0),
            "status": "Ready" if docker_result and docker_result["exit_code"] == 0 else STATUS_DOCKER_UNAVAILABLE,
            "executable": docker or "Not Found", "server": docker_result["stdout"] if docker_result else "Not tested"},
            "provenance": {"widget": "Docker & WSL2 Status", "timestamp_utc": _utc()}}

    @staticmethod
    def _port_open(port: int) -> bool:
        with socket.socket() as sock:
            sock.settimeout(0.2)
            return sock.connect_ex(("127.0.0.1", port)) == 0

    def inspect_process_supervisor_and_storage(self) -> dict[str, Any]:
        app_home = Path(os.environ.get("BIOINTEL_APP_HOME") or os.getcwd()).resolve()
        storage_root = app_home / "UserData" if (app_home / "UserData").exists() else app_home
        usage = shutil.disk_usage(storage_root)
        write_status = "Failed"
        try:
            with tempfile.NamedTemporaryFile(prefix="biointel_write_probe_", dir=storage_root, delete=True) as handle:
                handle.write(b"probe")
                handle.flush()
            write_status = "Passed"
        except OSError as exc:
            write_status = f"Failed: {type(exc).__name__}"
        processes = {
            "current_biointel_process": {"pid": os.getpid(), "status": "Running", "command": Path(sys.executable).name},
            "fastapi_backend": {"pid": None, "port": 8000, "status": "Listening" if self._port_open(8000) else "Not Detected"},
            "streamlit_ui": {"pid": None, "port": 8501, "status": "Listening" if self._port_open(8501) else "Not Detected"},
            "background_worker": {"pid": None, "status": "Not Detected", "note": "No validated worker PID file was found."},
        }
        return {"status": "Inspected", "processes": processes, "storage_health": {
            "drive": os.path.splitdrive(str(storage_root))[0] or str(storage_root.anchor),
            "total_gb": round(usage.total / 1024**3, 2), "free_gb": round(usage.free / 1024**3, 2),
            "used_gb": round(usage.used / 1024**3, 2), "write_test": write_status,
            "disk_full_warning": usage.free < 2 * 1024**3},
            "provenance": {"widget": "Process & Storage", "timestamp_utc": _utc()}}

    def audit_all_connectivity_widgets(self) -> dict[str, Any]:
        results = {"internet": self.check_internet_status(), "api_health_matrix": self.get_api_health_matrix(),
            "tls_proxy": self.inspect_tls_and_proxy(), "gpu": self.check_gpu_telemetry(),
            "docker_wsl2": self.inspect_docker_wsl2_status(),
            "supervisor_storage": self.inspect_process_supervisor_and_storage()}
        healthy = results["internet"]["status"] == STATUS_ONLINE
        return {"passed": healthy, "status": "Healthy" if healthy else "Degraded",
            "widgets_audited": len(results), "timestamp_utc": _utc(), "results": results}


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0