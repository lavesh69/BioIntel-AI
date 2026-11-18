from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def generate_slurm_job_script(job_name: str, command: str, nodes: int = 1, cpus: int = 8, memory_gb: int = 32, time_limit: str = "04:00:00") -> str:
    """Generates a Slurm sbatch script for HPC cluster execution."""
    return f"""#!/bin/bash
#SBATCH --job-name={job_name}
#SBATCH --nodes={nodes}
#SBATCH --cpus-per-task={cpus}
#SBATCH --mem={memory_gb}G
#SBATCH --time={time_limit}
#SBATCH --output=slurm-%j.out
#SBATCH --error=slurm-%j.err

echo "=== BioIntel HPC Slurm Execution Started ==="
echo "Node: $SLURMD_NODENAME | JobID: $SLURM_JOB_ID"
date

{command}

echo "=== BioIntel HPC Slurm Execution Finished ==="
"""


def generate_kubernetes_job_manifest(job_name: str, image: str, command_list: list[str]) -> dict[str, Any]:
    """Generates a Kubernetes Job YAML manifest for cloud cluster execution."""
    return {
        "apiVersion": "batch/v1",
        "kind": "Job",
        "metadata": {"name": f"biointel-job-{job_name}"},
        "spec": {
            "template": {
                "spec": {
                    "containers": [
                        {
                            "name": job_name,
                            "image": image,
                            "command": command_list,
                            "resources": {
                                "requests": {"cpu": "4", "memory": "16Gi"},
                                "limits": {"cpu": "16", "memory": "64Gi"},
                            },
                        }
                    ],
                    "restartPolicy": "Never",
                }
            },
            "backoffLimit": 2,
        },
    }
