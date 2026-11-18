"""Deterministic, isolated synthetic data for BioIntel Education."""

from .manifest import DEMO_BADGE, DEMO_SEED_VERSION, manifest
from .reset import reset_demo
from .seed import seed_demo

__all__ = [
    "DEMO_BADGE",
    "DEMO_SEED_VERSION",
    "manifest",
    "reset_demo",
    "seed_demo",
]
