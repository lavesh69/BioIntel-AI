"""
BioIntel AI — Dynamic Thread Pool & Hardware Core Tuner
Calculates optimal worker concurrency based on system CPU topology.
"""
from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor


class HardwareThreadPoolTuner:
    """Manages system CPU thread pool sizing and worker allocation."""

    @staticmethod
    def get_optimal_worker_count(io_bound: bool = True) -> int:
        """Returns the optimal worker count for CPU-bound or IO-bound operations."""
        cores = os.cpu_count() or 4
        if io_bound:
            return max(8, min(64, cores * 4))
        return max(2, cores)

    @classmethod
    def create_executor(cls, name_prefix: str = "biointel_worker", io_bound: bool = True) -> ThreadPoolExecutor:
        """Creates a tuned ThreadPoolExecutor instance."""
        workers = cls.get_optimal_worker_count(io_bound=io_bound)
        return ThreadPoolExecutor(max_workers=workers, thread_name_prefix=name_prefix)
