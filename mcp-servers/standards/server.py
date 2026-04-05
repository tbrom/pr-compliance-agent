import sys
import asyncio
from mcp.server.stdio import stdio_server
from mcp.server import Server
from mcp.types import Tool, TextContent
from knowledge_base import KnowledgeBase

kb = KnowledgeBase()
kb.load_rules_from_md("standards.md")

server = Server("sentinel-standards-mcp")

@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_security_standard",
            description="Get the definition and rules of a specific enterprise security standard (e.g. PCI-DSS, SOC2, OWASP, DATA_FABRIC).",
            inputSchema={
                "type": "object",
                "properties": {
                    "standard_name": {
                        "type": "string",
                        "description": "The name of the standard to retrieve (e.g., PCI-DSS, SOC2, DATA_FABRIC, OWASP)"
                    }
                },
                "required": ["standard_name"]
            }
        ),
        Tool(
            name="search_compliance_standards",
            description="Perform a semantic search across all enterprise compliance standards to find rules relevant to a specific code diff.",
            inputSchema={
                "type": "object",
                "properties": {
                    "code_diff": {
                        "type": "string",
                        "description": "The content of the pull request code diff to match against standards."
                    }
                },
                "required": ["code_diff"]
            }
        )
    ]

@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    if name == "get_security_standard":
        standard_name = (arguments or {}).get("standard_name", "")
        result = kb.get_standard(standard_name or "")
        return [TextContent(type="text", text=str(result))]
    elif name == "search_compliance_standards":
        code_diff = (arguments or {}).get("code_diff", "")
        results = kb.search_rules(code_diff or "")
        return [TextContent(type="text", text="\n".join(results))]
    raise ValueError(f"Unknown tool: {name}")

async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options()
        )

if __name__ == "__main__":
    asyncio.run(main())
