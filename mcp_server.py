
from mcp.server.fastmcp import FastMCP
from ddgs import DDGS
from rag.retriever import search_documents
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


@mcp.tool()
def search_pdf_documents(query: str, top_k: int = 5) -> dict:
    """Search indexed PDF documents and return relevant text with page numbers."""
    return search_documents(query, top_k=top_k)

if __name__ == "__main__":
    mcp.run(transport="stdio")