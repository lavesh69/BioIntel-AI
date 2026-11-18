from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger("biointel.shiro.copilot_safety")


class ShiroCopilotSafetyGuardrails:
    """Safety & Permission Enforcement for Shiro Scientific Copilot."""

    ALLOWED_READ_TOOLS = ["search_modules", "view_workflow_provenance", "check_engine_status", "read_benchmark_score"]
    PROTECTED_WRITE_TOOLS = ["execute_workflow", "approve_scientific_review", "delete_dataset", "modify_rbac_role"]

    def __init__(self, user_role: str = "Scientist"):
        self.user_role = user_role

    def validate_tool_execution(self, tool_name: str, parameters: Dict[str, Any]) -> Dict[str, Any]:
        """Enforce tool permission boundaries and action confirmation."""
        if tool_name in self.ALLOWED_READ_TOOLS:
            return {"allowed": True, "action": tool_name, "requires_confirmation": False}

        if tool_name in self.PROTECTED_WRITE_TOOLS:
            if self.user_role not in ["Admin", "Scientist"]:
                return {
                    "allowed": False,
                    "reason": f"Role '{self.user_role}' lacks permission for protected action '{tool_name}'",
                }
            return {"allowed": True, "action": tool_name, "requires_confirmation": True}

        return {"allowed": True, "action": tool_name, "requires_confirmation": False}
