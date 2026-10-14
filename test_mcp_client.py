
import asyncio
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def main():
    server_file = Path(__file__).with_name("mcp_server.py")

    server_params = StdioServerParameters(
        command=sys.executable,
        args=[str(server_file)],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            print("Connected to MCP server successfully!")

            result = await session.list_tools()

            print("\nAvailable MCP tools:")
            for tool in result.tools:
                print(f"- {tool.name}: {tool.description}")

            print("\nTesting web_search...")
            search_result = await session.call_tool(
                "web_search",
                {
                    "query": "Python programming language",
                    "max_results": 2,
                },
            )

            for item in search_result.content:
                if hasattr(item, "text"):
                    print(item.text)

            if search_result.isError:
                print("The MCP tool reported an error.")


if __name__ == "__main__":
    asyncio.run(main())