import sys
import asyncio
from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent

server = Server("sentinel-observability-mcp")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_production_logs",
            description="Fetch Datadog or GCP Cloud Trace logs surrounding a specific service to evaluate PR stability.",
            inputSchema={
                "type": "object",
                "properties": {
                    "service_name": {"type": "string", "description": "e.g., auth-service, payment-gateway"}
                },
                "required": ["service_name"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name == "get_production_logs":
        service = (arguments or {}).get("service_name", "")
        # Mock Context
        return [TextContent(type="text", text=f"Log query for {service}: 0 critical errors in the last 24 hours. Normal latency distributions (p95: 45ms).")]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, server.create_initialization_options())

if __name__ == "__main__":
    asyncio.run(main())
