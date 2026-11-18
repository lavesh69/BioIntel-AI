from __future__ import annotations

import hashlib
import json
import logging
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

logger = logging.getLogger("biointel.security.enterprise_rbac")

ROLES = {
    "Admin": ["read", "write", "delete", "admin", "manage_tenants", "manage_roles"],
    "Scientist": ["read", "write", "execute_jobs", "export_data"],
    "Analyst": ["read", "write", "view_reports"],
    "Reviewer": ["read", "comment", "approve_workflow"],
    "Viewer": ["read"],
}


@dataclass
class UserContext:
    user_id: str
    username: str
    role: str
    tenant_id: str

    def has_permission(self, permission: str) -> bool:
        allowed_permissions = ROLES.get(self.role, [])
        return permission in allowed_permissions or "admin" in allowed_permissions


class MultiTenantIsolationManager:
    """Manages tenant isolation boundaries and cross-tenant leakage prevention."""

    def __init__(self):
        self.tenants: Dict[str, Dict[str, Any]] = {
            "org-default": {"name": "Default Research Lab", "quota_mb": 10240, "created_at": "2026-01-01T00:00:00Z"},
            "org-demo": {"name": "Demo Biotech Inc", "quota_mb": 5120, "created_at": "2026-01-01T00:00:00Z"},
        }

    def validate_tenant_access(self, user_ctx: UserContext, target_tenant_id: str) -> bool:
        """Prevent cross-tenant data access unless user has Admin role."""
        if user_ctx.role == "Admin":
            return True
        return user_ctx.tenant_id == target_tenant_id


class LiveWorkspaceCollaborationEngine:
    """Multi-user presence, optimistic locking, and conflict resolution manager."""

    def __init__(self):
        self.active_sessions: Dict[str, Dict[str, Any]] = {}
        self.document_locks: Dict[str, str] = {}

    def join_workspace(self, workspace_id: str, user_ctx: UserContext) -> Dict[str, Any]:
        session_key = f"{workspace_id}:{user_ctx.user_id}"
        self.active_sessions[session_key] = {
            "workspace_id": workspace_id,
            "user_id": user_ctx.user_id,
            "username": user_ctx.username,
            "joined_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        return {
            "status": "Joined",
            "session_key": session_key,
            "active_users": [s["username"] for s in self.active_sessions.values() if s["workspace_id"] == workspace_id],
        }

    def acquire_lock(self, resource_id: str, user_id: str) -> bool:
        current_owner = self.document_locks.get(resource_id)
        if current_owner is None or current_owner == user_id:
            self.document_locks[resource_id] = user_id
            return True
        return False
