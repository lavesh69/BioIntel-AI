"""Step208 maximum-potential scientific feature pack.

The package contains local, deterministic research-software workflows. Optional
native-format dependencies are isolated and never required for core startup.
"""

from .execution import execute_feature
from .ingestion import FORMAT_CAPABILITIES, format_support_table, load_preview, stage_stream

__all__ = ["FORMAT_CAPABILITIES", "execute_feature", "format_support_table", "load_preview", "stage_stream"]
