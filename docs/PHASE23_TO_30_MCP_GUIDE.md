# Phase 23–30 MCP Guide

Configure `BIOINTEL_MCP_PRINCIPAL`, `BIOINTEL_MCP_INSTITUTION` and `BIOINTEL_MCP_API_KEY`, then run `RUN_BIOINTEL_MCP_WINDOWS.bat`.

The server uses JSON-RPC over stdio and supports `initialize`, `ping`, `tools/list` and `tools/call`. The API key must hold the underlying read/write scope and the principal must have an enabled MCP policy for each tool.

Tools are read-only by default. Write tools require an administrator policy and explicit human approval on the call. Shell commands, arbitrary SQL and unrestricted file access are not exposed.

