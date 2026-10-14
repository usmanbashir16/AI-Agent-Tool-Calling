
from ddgs import DDGS


def web_search(query, max_results=5):
    """Search the web and return relevant search results."""

    query = str(query).strip()

    if not query:
        return {"error": "Search query cannot be empty."}

    try:
        results = DDGS().text(
            query,
            max_results=max_results,
        )

        formatted_results = []

        for result in results:
            formatted_results.append({
                "title": result.get("title", ""),
                "url": result.get("href", ""),
                "snippet": result.get("body", ""),
            })

        if not formatted_results:
            return {
                "query": query,
                "message": "No search results found.",
                "results": [],
            }

        return {
            "query": query,
            "results": formatted_results,
        }

    except Exception as error:
        return {
            "error": f"Web search failed: {error}"
        }


if __name__ == "__main__":
    query = input("Enter your search query: ").strip()

    results = web_search(query)

    print("\nSearch Results:\n")
    print(results)