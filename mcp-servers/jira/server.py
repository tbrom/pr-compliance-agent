import sys
import asyncio
from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("sentinel-jira-mcp")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_jira_issue",
            description="Fetch a Jira issue summary and description to cross-reference with PR modifications.",
            inputSchema={
                "type": "object",
                "properties": {
                    "issue_id": {"type": "string", "description": "The Jira ID (e.g. STNL-123)"}
                },
                "required": ["issue_id"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name == "get_jira_issue":
        issue_id = (arguments or {}).get("issue_id", "")
        # Mock Context
        return [TextContent(type="text", text=f"Jira Context for {issue_id}: Implement Role-Based Access Control logic for the GCP Cloud Run deployment endpoints.")]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
