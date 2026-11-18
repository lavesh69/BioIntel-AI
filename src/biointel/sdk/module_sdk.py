from __future__ import annotations

import abc
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("biointel.sdk.module_sdk")


@dataclass
class ModuleMetadata:
    module_id: str
    name: str
    version: str
    description: str
    author: str
    category: str
    permissions: List[str]


class BioIntelModuleSDK(abc.ABC):
    """Abstract base class for extensible BioIntel AI modules."""

    def __init__(self, metadata: ModuleMetadata):
        self.metadata = metadata

    @abc.abstractmethod
    def get_input_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for input validation."""
        pass

    @abc.abstractmethod
    def get_output_schema(self) -> Dict[str, Any]:
        """Return JSON Schema for output validation."""
        pass

    @abc.abstractmethod
    def run(self, inputs: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        """Execute module logic and return outputs."""
        pass

    def health_check(self) -> Dict[str, Any]:
        return {"status": "HEALTHY", "module_id": self.metadata.module_id, "version": self.metadata.version}


class CentralDatasetGovernanceRegistry:
    """Central Dataset Registry & Governance Manager."""

    def __init__(self):
        self.datasets: Dict[str, Dict[str, Any]] = {}

    def register_dataset(self, dataset_id: str, name: str, genome_build: str, consent_category: str, file_path: str) -> Dict[str, Any]:
        h = hashlib.sha256(dataset_id.encode()).hexdigest()[:16]
        entry = {
            "dataset_id": dataset_id,
            "name": name,
            "genome_build": genome_build,
            "consent_category": consent_category,
            "file_path": file_path,
            "sha256": h,
            "legal_hold": False,
            "status": "REGISTERED",
        }
        self.datasets[dataset_id] = entry
        return entry
