"""
Sentinel MCP client.

Manages long-lived stdio connections to the Sentinel MCP servers
(Jira, Standards) and exposes typed helpers for the agent nodes.

One client instance is created during app startup and held on
`app.state.mcp_client`. A module-level accessor (`get_client`) is also
exposed so LangGraph nodes — which only receive the state dict — can
reach the client without threading it through `SentinelState`.
"""

from __future__ import annotations

import logging
import os
import sys
from contextlib import AsyncExitStack
from typing import Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger("sentinel")

_instance: Optional["SentinelMCPClient"] = None


def _default_mcp_root() -> str:
    # orchestrator/ and mcp-servers/ are siblings in the repo
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.normpath(os.path.join(here, "..", "mcp-servers"))


def _default_python_bin(mcp_root: str) -> str:
    # Prefer the mcp-servers venv if it exists (it has chromadb + sentence-transformers).
    venv_python = os.path.join(mcp_root, "venv", "bin", "python")
    if os.path.exists(venv_python):
        return venv_python
    return os.environ.get("MCP_PYTHON_BIN", sys.executable)


class SentinelMCPClient:
    """Long-lived MCP client holding one session per server."""

    def __init__(self, mcp_root: Optional[str] = None, python_bin: Optional[str] = None):
        self.mcp_root = mcp_root or os.environ.get("MCP_ROOT") or _default_mcp_root()
        self.python_bin = python_bin or _default_python_bin(self.mcp_root)
        self.sessions: dict[str, ClientSession] = {}
        self._stack: Optional[AsyncExitStack] = None

    async def start(self) -> None:
        """Spawn every MCP server subprocess and initialize its session."""
        stack = AsyncExitStack()
        await stack.__aenter__()
        self._stack = stack

        servers = {
            "jira": os.path.join(self.mcp_root, "jira", "server.py"),
            "standards": os.path.join(self.mcp_root, "standards", "server.py"),
        }

        for name, script in servers.items():
            if not os.path.exists(script):
                logger.warning("⚠️  MCP server script missing: %s", script)
                continue
            try:
                params = StdioServerParameters(
                    command=self.python_bin,
                    args=[script],
                )
                read, write = await stack.enter_async_context(stdio_client(params))
                session = await stack.enter_async_context(ClientSession(read, write))
                await session.initialize()
                self.sessions[name] = session
                logger.info("✅ MCP session started: %s (%s)", name, script)
            except Exception as e:
                logger.error("❌ Failed to start MCP server %s: %s", name, e)

    async def stop(self) -> None:
        if self._stack is not None:
            await self._stack.aclose()
            self._stack = None
            self.sessions.clear()
            logger.info("🛑 MCP sessions closed")

    @staticmethod
    def _extract_text(result) -> str:
        parts: list[str] = []
        for item in getattr(result, "content", []) or []:
            text = getattr(item, "text", None)
            if text:
                parts.append(text)
        return "\n".join(parts).strip()

    async def get_jira_issue(self, issue_id: str) -> Optional[str]:
        session = self.sessions.get("jira")
        if session is None:
            return None
        try:
            result = await session.call_tool("get_jira_issue", {"issue_id": issue_id})
            return self._extract_text(result) or None
        except Exception as e:
            logger.error("❌ MCP get_jira_issue failed for %s: %s", issue_id, e)
            return None

    async def search_compliance_standards(self, code_diff: str) -> Optional[str]:
        session = self.sessions.get("standards")
        if session is None:
            return None
        try:
            result = await session.call_tool(
                "search_compliance_standards",
                {"code_diff": code_diff},
            )
            return self._extract_text(result) or None
        except Exception as e:
            logger.error("❌ MCP search_compliance_standards failed: %s", e)
            return None


def set_client(client: SentinelMCPClient) -> None:
    global _instance
    _instance = client


def get_client() -> Optional[SentinelMCPClient]:
    return _instance
