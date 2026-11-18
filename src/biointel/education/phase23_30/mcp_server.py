from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import Any, TextIO

from ..platform import EducationError
from .api import service as api_service
from .integration import MCP_TOOLS
from .service import EducationEnterprisePlatform

TOOL_API_SCOPES = {
    "search_courses": "courses:read",
    "read_course_material": "courses:read",
    "search_science_pulse": "science:read",
    "query_approved_shiro": "courses:read",
    "retrieve_assignment_status": "assignments:read",
    "retrieve_student_progress": "results:read",
    "retrieve_project_metadata": "science:read",
    "create_draft_lesson": "courses:write",
    "create_draft_quiz": "courses:write",
    "create_support_ticket": "support:write",
    "start_approved_agent_task": "agent_tasks:write",
}


@dataclass
class MCPApplication:
    platform: EducationEnterprisePlatform
    principal_id: str
    institution_id: str
    api_key: str

    def _allowed_tools(self) -> list[dict[str, Any]]:
        policies = self.platform._all(
            """SELECT * FROM education_p30_mcp_policies
            WHERE institution_id=? AND principal_id=? AND allowed=1
            ORDER BY tool_key""",
            (self.institution_id, self.principal_id),
        )
        output = []
        for policy in policies:
            key = str(policy["tool_key"])
            definition = MCP_TOOLS.get(key)
            if not definition:
                continue
            output.append(
                {
                    "name": key,
                    "description": (
                        f"BioIntel tenant-scoped {key.replace('_', ' ')}. "
                        f"Write operation: {bool(definition['write'])}."
                    ),
                    "inputSchema": {
                        "type": "object",
                        "additionalProperties": True,
                    },
                    "annotations": {
                        "readOnlyHint": not bool(definition["write"]),
                        "destructiveHint": False,
                        "idempotentHint": not bool(definition["write"]),
                    },
                }
            )
        return output

    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        request_id = request.get("id")
        method = str(request.get("method", ""))
        try:
            if method == "notifications/initialized":
                return None
            if method == "initialize":
                result = {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {
                        "name": "biointel-education-phase23-30",
                        "version": "15.6.0-phase30",
                    },
                }
            elif method == "tools/list":
                result = {"tools": self._allowed_tools()}
            elif method == "tools/call":
                params = dict(request.get("params") or {})
                tool = str(params.get("name", ""))
                arguments = dict(params.get("arguments") or {})
                if tool not in TOOL_API_SCOPES:
                    raise EducationError("Unknown MCP tool.")
                auth = self.platform.authenticate_api_key(
                    self.api_key,
                    required_scope=TOOL_API_SCOPES[tool],
                    route=f"mcp://tools/{tool}",
                    method="CALL",
                    request_id=str(request_id or ""),
                )
                if auth["institution_id"] != self.institution_id:
                    raise EducationError("MCP API key tenant mismatch.")
                human_approved = bool(arguments.pop("_human_approved", False))
                called = self.platform.call_mcp_tool(
                    self.principal_id,
                    self.institution_id,
                    tool,
                    arguments,
                    human_approved=human_approved,
                )
                result = {
                    "content": [
                        {
                            "type": "text",
                            "text": json.dumps(called, ensure_ascii=False),
                        }
                    ],
                    "isError": False,
                }
            elif method == "ping":
                result = {}
            else:
                return {
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": "Method not found."},
                }
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except EducationError as exc:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32001,
                    "message": str(exc),
                    "data": {
                        "safe": True,
                        "arbitrary_code_execution": False,
                    },
                },
            }
        except Exception:
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": "Internal BioIntel MCP error.",
                    "data": {"safe": True},
                },
            }


def application_from_environment() -> MCPApplication:
    principal = os.getenv("BIOINTEL_MCP_PRINCIPAL", "").strip()
    institution = os.getenv("BIOINTEL_MCP_INSTITUTION", "").strip()
    api_key = os.getenv("BIOINTEL_MCP_API_KEY", "").strip()
    if not principal or not institution or not api_key:
        raise EducationError(
            "BIOINTEL_MCP_PRINCIPAL, BIOINTEL_MCP_INSTITUTION and "
            "BIOINTEL_MCP_API_KEY are required."
        )
    return MCPApplication(
        platform=api_service(),
        principal_id=principal,
        institution_id=institution,
        api_key=api_key,
    )


def serve_stdio(
    application: MCPApplication,
    incoming: TextIO = sys.stdin,
    outgoing: TextIO = sys.stdout,
) -> int:
    for line in incoming:
        text = line.strip()
        if not text:
            continue
        try:
            request = json.loads(text)
            if not isinstance(request, dict):
                raise ValueError
        except (ValueError, json.JSONDecodeError):
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": "Parse error."},
            }
        else:
            response = application.handle(request)
        if response is not None:
            outgoing.write(json.dumps(response, ensure_ascii=False) + "\n")
            outgoing.flush()
    return 0


def main() -> int:
    if "--diagnose" in sys.argv:
        try:
            application = application_from_environment()
            tools = application._allowed_tools()
        except EducationError as exc:
            print(json.dumps({"ok": False, "error": str(exc)}))
            return 2
        print(
            json.dumps(
                {
                    "ok": True,
                    "transport": "stdio",
                    "principal": application.principal_id,
                    "institution": application.institution_id,
                    "allowed_tools": [tool["name"] for tool in tools],
                    "arbitrary_code_execution": False,
                }
            )
        )
        return 0
    return serve_stdio(application_from_environment())


if __name__ == "__main__":
    raise SystemExit(main())
