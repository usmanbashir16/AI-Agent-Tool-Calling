
from main import initialize_database
from vector_memory import (
    sync_sqlite_conversations,
    search_vector_conversations,
)

initialize_database()

print("\nSyncing conversation history...")
sync_sqlite_conversations()

query = (
    "What feature did we use to check atmospheric "
    "conditions for a location?"
)

print(f"\nSemantic search query: {query}")

results = search_vector_conversations(query, limit=5)

if not results:
    print("No relevant conversations found.")
else:
    for result in results:
        print("\n" + "-" * 50)
        print("Role:", result["role"])
        print("Date:", result["created_at"])
        print("Distance:", result["distance"])
        print("Message:", result["content"])