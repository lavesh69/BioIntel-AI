"""
BioIntel AI 15.6.0 — GPU & CUDA Acceleration Engine
Provides NVIDIA CUDA detection, total/available VRAM monitoring, PyTorch/TensorFlow GPU device selection,
CPU fallback, batch size tuning with Out-Of-Memory (OOM) retry logic, and GPU cache cleanup.
"""

import sys
import time
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger("biointel.hardware.gpu_acceleration")


class GPUAccelerationEngine:
    """NVIDIA CUDA & PyTorch GPU acceleration manager with CPU fallback and OOM safety."""

    def __init__(self):
        self._inspect_gpu_hardware()

    def _inspect_gpu_hardware(self):
        self.cuda_available = False
        self.device_name = "CPU (Native Fallback)"
        self.device_count = 0
        self.total_vram_mb = 0.0
        self.free_vram_mb = 0.0
        self.cuda_version = "None"

        # 1. PyTorch CUDA inspection
        try:
            import torch
            if torch.cuda.is_available():
                self.cuda_available = True
                self.device_count = torch.cuda.device_count()
                self.device_name = torch.cuda.get_device_name(0)
                self.cuda_version = torch.version.cuda or "Unknown"

                props = torch.cuda.get_device_properties(0)
                self.total_vram_mb = round(props.total_memory / (1024 * 1024), 2)
                self.free_vram_mb = round(torch.cuda.mem_get_info()[0] / (1024 * 1024), 2)
        except Exception as e:
            logger.info(f"PyTorch CUDA probe fallback: {e}")

        # 2. pynvml / nvidia-smi fallback if PyTorch CUDA not loaded
        if not self.cuda_available:
            try:
                import pynvml
                pynvml.nvmlInit()
                handle = pynvml.nvmlDeviceGetHandleByIndex(0)
                self.cuda_available = True
                self.device_count = pynvml.nvmlDeviceGetCount()
                self.device_name = pynvml.nvmlDeviceGetName(handle).decode("utf-8")
                info = pynvml.nvmlDeviceGetMemoryInfo(handle)
                self.total_vram_mb = round(info.total / (1024 * 1024), 2)
                self.free_vram_mb = round(info.free / (1024 * 1024), 2)
            except Exception:
                pass

    def get_hardware_status(self) -> Dict[str, Any]:
        """Return diagnostic GPU hardware status and VRAM metrics."""
        return {
            "gpu_available": self.cuda_available,
            "device_name": self.device_name,
            "device_count": self.device_count,
            "cuda_version": self.cuda_version,
            "total_vram_mb": self.total_vram_mb,
            "free_vram_mb": self.free_vram_mb,
            "execution_device": "cuda:0" if self.cuda_available else "cpu",
            "status_label": "GPU Accelerated" if self.cuda_available else "GPU Unavailable — CPU Fallback Active",
        }

    def execute_with_oom_retry(self, fn, initial_batch_size: int = 32, *args, **kwargs) -> Dict[str, Any]:
        """Execute a PyTorch/model function with automatic batch size reduction on CUDA Out-Of-Memory (OOM)."""
        current_batch = initial_batch_size
        attempts = 0
        max_attempts = 4

        start_time = time.time()
        while current_batch >= 1 and attempts < max_attempts:
            attempts += 1
            try:
                result = fn(batch_size=current_batch, device="cuda" if self.cuda_available else "cpu", *args, **kwargs)
                elapsed = time.time() - start_time
                return {
                    "status": "Completed",
                    "result": result,
                    "batch_size_used": current_batch,
                    "oom_retries": attempts - 1,
                    "device": "cuda" if self.cuda_available else "cpu",
                    "elapsed_seconds": round(elapsed, 2),
                }
            except Exception as e:
                err_str = str(e).lower()
                if "out of memory" in err_str or "oom" in err_str:
                    logger.warning(f"CUDA OOM detected at batch size {current_batch}. Retrying with batch size {current_batch // 2}...")
                    self.clear_gpu_cache()
                    current_batch //= 2
                else:
                    return {
                        "status": "Failed",
                        "error": str(e),
                        "device": "cuda" if self.cuda_available else "cpu",
                    }

        return {
            "status": "Failed",
            "error": f"Execution failed after OOM retries. Minimum batch size 1 exceeded.",
        }

    def clear_gpu_cache(self):
        """Clean PyTorch CUDA memory cache."""
        if self.cuda_available:
            try:
                import torch
                torch.cuda.empty_cache()
            except Exception:
                pass


if __name__ == "__main__":
    engine = GPUAccelerationEngine()
    print("GPU Status Probes:")
    print(json.dumps(engine.get_hardware_status(), indent=2))
