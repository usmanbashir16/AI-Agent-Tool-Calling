
from mcp.server.fastmcp import FastMCP
from ddgs import DDGS

mcp = FastMCP("usman-ai-agent")


@mcp.tool()
def web_search(query: str, max_results: int = 5) -> dict:
    """Search the web and return titles, URLs, and snippets."""

    if not query or not query.strip():
        return {"error": "Search query cannot be empty."}

    max_results = max(1, min(int(max_results), 5))

    try:
        
        with DDGS() as ddgs:
            results = list(
                ddgs.text(
                    query.strip(),
                    max_results=max_results,
                )
            )

        return {
            "query": query,
            "results": [
                {
                    "title": item.get("title", ""),
                    "url": item.get("href", ""),
                    "snippet": item.get("body", ""),
                }
                for item in results
            ],
        }

    except Exception as error:
        return {"error": f"Web search failed: {error}"}


if __name__ == "__main__":
    mcp.run(transport="stdio")