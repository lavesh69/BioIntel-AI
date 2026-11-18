"""
BioIntel AI — Memory & Garbage Collection Optimizer
Trims unused heap allocations and forces garbage collection after background jobs.
"""
from __future__ import annotations

import gc
import os, sys


class MemoryOptimizer:
    """Manages memory trim and garbage collection cycles."""

    @staticmethod
    def collect() -> dict[str, int]:
        """Runs full garbage collection sweep across all generations."""
        unreachable = gc.collect()
        return {"unreachable_objects_freed": unreachable}

    @staticmethod
    def trim_heap() -> None:
        """Trims process memory allocators when supported on platform."""
        try:
            if hasattr(sys, "getwindowsversion"):
                import ctypes
                ctypes.windll.psapi.EmptyWorkingSet(ctypes.windll.kernel32.GetCurrentProcess())
        except Exception:
            pass
