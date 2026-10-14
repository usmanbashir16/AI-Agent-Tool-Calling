
import sqlite3
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


# =========================================================
# CONFIGURATION
# =========================================================

BASE_DIR = Path(__file__).resolve().parent
SQLITE_DB = BASE_DIR / "memory.db"
CHROMA_DB = BASE_DIR / "chroma_db"

client = chromadb.PersistentClient(path=str(CHROMA_DB))

collection = client.get_or_create_collection(
    name="agent_memories",
    metadata={"hnsw:space": "cosine"},
)

conversation_collection = client.get_or_create_collection(
    name="agent_conversations",
    metadata={"hnsw:space": "cosine"},
)
print("Loading embedding model...")
model = SentenceTransformer("all-MiniLM-L6-v2")
print("Embedding model loaded!")


# =========================================================
# HELPER
# =========================================================

def normalize_key(key):
    return key.strip().lower().replace(" ", "_")


# =========================================================
# SAVE / UPDATE VECTOR MEMORY
# =========================================================

def save_vector_memory(key, value):
    """Save or update a memory in ChromaDB."""
    key = normalize_key(key)
    value = str(value).strip()

    if not key or not value:
        raise ValueError("Memory key and value cannot be empty.")

    memory_text = f"{key.replace('_', ' ')}: {value}"
    embedding = model.encode(memory_text).tolist()

    collection.upsert(
        ids=[key],
        documents=[memory_text],
        embeddings=[embedding],
        metadatas=[{
            "key": key,
            "value": value,
        }],
    )

    return f"Vector memory saved: {key} = {value}"


# =========================================================
# DELETE VECTOR MEMORY
# =========================================================

def delete_vector_memory(key):
    """Delete a memory from ChromaDB."""
    key = normalize_key(key)

    existing = collection.get(ids=[key])

    if not existing["ids"]:
        return f"No vector memory found for key: {key}"

    collection.delete(ids=[key])
    return f"Vector memory deleted: {key}"


# =========================================================
# SEMANTIC SEARCH
# =========================================================

def search_vector_memories(query, limit=3):
    """Find memories based on semantic similarity."""
    if collection.count() == 0:
        return []

    query_embedding = model.encode(query).tolist()

    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(limit, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    memories = []

    for metadata, document, distance in zip(
        results["metadatas"][0],
        results["documents"][0],
        results["distances"][0],
    ):
        if metadata is None:
            continue

        memories.append({
            "key": metadata["key"],
            "value": metadata["value"],
            "document": document,
            "distance": round(float(distance), 4),
        })

    return memories


# =========================================================
# SQLITE -> CHROMADB SYNC
# =========================================================

def sync_sqlite_memories():
    """Synchronize SQLite memories into ChromaDB."""
    if not SQLITE_DB.exists():
        print("SQLite database not found. Nothing to sync.")
        return 0

    with sqlite3.connect(str(SQLITE_DB)) as connection:
        rows = connection.execute(
            "SELECT memory_key, memory_value FROM memories"
        ).fetchall()

    # Upsert current SQLite memories.
    for key, value in rows:
        save_vector_memory(key, value)

    # Remove vector records no longer present in SQLite.
    sqlite_keys = {normalize_key(row[0]) for row in rows}
    vector_records = collection.get(include=["metadatas"])

    stale_ids = [
        vector_id
        for vector_id, metadata in zip(
            vector_records["ids"],
            vector_records["metadatas"],
        )
        if vector_id not in sqlite_keys
    ]

    if stale_ids:
        collection.delete(ids=stale_ids)

    print(
        f"Sync complete: {len(rows)} SQLite memories "
        "synchronized with ChromaDB."
    )

    return len(rows)


def sync_sqlite_conversations():
    """Sync SQLite conversation history into its own ChromaDB collection."""
    import sqlite3
    from main import DB_PATH

    with sqlite3.connect(DB_PATH) as connection:
        rows = connection.execute(
            """
            SELECT id, role, content, created_at
            FROM conversation_history
            ORDER BY id
            """
        ).fetchall()

    if not rows:
        # Remove any old vector records if SQLite history is empty.
        existing = conversation_collection.get()
        if existing["ids"]:
            conversation_collection.delete(ids=existing["ids"])
        print("No conversation history to synchronize.")
        return 0

    ids = []
    documents = []
    embeddings = []
    metadatas = []

    for message_id, role, content, created_at in rows:
        document_id = f"chat_{message_id}"
        ids.append(document_id)
        documents.append(content)

        # Include the role in the embedding so user and assistant
        # messages are represented with their context.
        embedding_text = f"{role}: {content}"
        embeddings.append(
            model.encode(embedding_text).tolist()
        )
        metadatas.append({
            "sqlite_id": message_id,
            "role": role,
            "created_at": created_at,
        })

    conversation_collection.upsert(
        ids=ids,
        documents=documents,
        embeddings=embeddings,
        metadatas=metadatas,
    )

    # Remove ChromaDB records that no longer exist in SQLite.
    existing_ids = conversation_collection.get()["ids"]
    current_ids = set(ids)
    stale_ids = [
        item_id for item_id in existing_ids
        if item_id not in current_ids
    ]

    if stale_ids:
        conversation_collection.delete(ids=stale_ids)

    print(f"Synchronized {len(rows)} conversation messages.")
    return len(rows)



def search_vector_conversations(query, limit=5):
    """Find relevant messages from conversation history."""

    if not query or not query.strip():
        return []

    limit = max(1, min(int(limit), 10))
    total = conversation_collection.count()

    if total == 0:
        return []

    query_embedding = model.encode(query).tolist()

    # Retrieve more candidates so we can filter and rerank them.
    candidate_count = min(max(limit * 4, 20), total)

    results = conversation_collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        include=["documents", "metadatas", "distances"],
    )

    matches = []

    query_lower = query.lower()

    technical_terms = [
        "sqlite",
        "chromadb",
        "embedding",
        "embeddings",
        "conversation_history",
        "agent_conversations",
        "search_vector_conversations",
        "sync_sqlite_conversations",
        "semantic_conversation_search",
        "sentence-transformers",
        "all-minilm-l6-v2",
    ]

    for i, content in enumerate(results["documents"][0]):
        metadata = results["metadatas"][0][i]
        distance = results["distances"][0][i]
        content_lower = content.lower()

        # Skip weak matches.
        if distance > 0.75:
            continue

        # Prefer messages that contain implementation details.
        technical_matches = [
            term for term in technical_terms
            if term in content_lower
        ]

        score = 1.0 - distance
        score += min(len(technical_matches) * 0.08, 0.32)

        # Prefer messages that directly answer the query.
        if query_lower in content_lower:
            score += 0.2

        # Reduce priority of unsupported negative claims.
        negative_phrases = [
            "haven't discussed",
            "haven't previously discussed",
            "haven't actually discussed",
            "haven't discussed building",
        ]

        if any(
            phrase in content_lower
            for phrase in negative_phrases
        ):
            score -= 0.25

        matches.append({
            "id": metadata["sqlite_id"],
            "role": metadata["role"],
            "content": content,
            "created_at": metadata["created_at"],
            "distance": round(distance, 4),
            "score": round(score, 4),
            "technical_matches": technical_matches,
        })

    # Rank by relevance, then prefer newer messages.
    matches.sort(
        key=lambda item: (item["score"], item["id"]),
        reverse=True,
    )

    return matches[:limit]
# =========================================================
# STANDALONE TEST
# =========================================================

if __name__ == "__main__":
    print("\nSynchronizing memories...")
    sync_sqlite_memories()

    query = "Which coding language do I prefer?"
    print(f"\nSemantic search query: {query}")

    for memory in search_vector_memories(query):
        print(memory)