
import math
import re
from collections import Counter
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer


BASE_DIR = Path(__file__).resolve().parent.parent
CHROMA_DB_PATH = BASE_DIR / "chroma_db"

client = chromadb.PersistentClient(path=str(CHROMA_DB_PATH))

collection = client.get_or_create_collection(
    name="agent_documents",
    metadata={"hnsw:space": "cosine"},
)

_model = None

STOP_WORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been",
    "do", "does", "did", "what", "where", "when", "who", "whom",
    "which", "how", "why", "can", "could", "would", "should",
    "i", "we", "you", "he", "she", "they", "it", "his", "her",
    "their", "my", "our", "and", "or", "but", "of", "to", "in",
    "on", "at", "for", "from", "with", "about", "me", "tell",
    "find", "please", "document", "file", "section",
}


def get_embedding_model():
    global _model

    if _model is None:
        _model = SentenceTransformer("all-MiniLM-L6-v2")

    return _model


def tokenize(text: str) -> list[str]:
    """Tokenize text for general-purpose keyword retrieval."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return [word for word in words if word not in STOP_WORDS]


def bm25_scores(
    query: str,
    documents: list[str],
    k1: float = 1.5,
    b: float = 0.75,
) -> list[float]:
    """Calculate BM25 relevance scores for a collection of text chunks."""
    query_terms = set(tokenize(query))
    tokenized_docs = [tokenize(doc or "") for doc in documents]

    if not query_terms or not tokenized_docs:
        return [0.0] * len(documents)

    doc_lengths = [len(doc) for doc in tokenized_docs]
    average_length = sum(doc_lengths) / len(doc_lengths)

    document_frequencies = Counter()

    for tokens in tokenized_docs:
        document_frequencies.update(set(tokens))

    scores = []

    for tokens, doc_length in zip(tokenized_docs, doc_lengths):
        frequencies = Counter(tokens)
        score = 0.0

        for term in query_terms:
            frequency = frequencies.get(term, 0)

            if frequency == 0:
                continue

            df = document_frequencies[term]
            idf = math.log(
                1 + (len(tokenized_docs) - df + 0.5) / (df + 0.5)
            )

            length_normalizer = (
                frequency
                + k1 * (
                    1 - b
                    + b * doc_length / max(average_length, 1)
                )
            )

            score += (
                idf
                * frequency
                * (k1 + 1)
                / length_normalizer
            )

        scores.append(score)

    return scores


def search_documents(
    query: str,
    top_k: int = 5,
    filename: str | None = None,
) -> dict:
    """Combine semantic retrieval and BM25 keyword retrieval."""

    query = query.strip()

    if not query:
        raise ValueError("Search query cannot be empty.")

    if not 1 <= top_k <= 20:
        raise ValueError("top_k must be between 1 and 20.")

    where_filter = {"filename": filename} if filename else None

    # Retrieve the indexed chunks for keyword search.
    stored = collection.get(
        where=where_filter,
        include=["documents", "metadatas"],
    )

    ids = stored.get("ids", [])
    documents = stored.get("documents", [])
    metadatas = stored.get("metadatas", [])

    if not documents:
        return {
            "query": query,
            "results": [],
            "message": "No matching PDF documents have been indexed.",
        }

    model = get_embedding_model()

    query_embedding = model.encode(
        query,
        normalize_embeddings=True,
    ).tolist()

    candidate_count = min(max(top_k * 5, 25), len(documents))

    semantic_result = collection.query(
        query_embeddings=[query_embedding],
        n_results=candidate_count,
        where=where_filter,
        include=["documents", "metadatas", "distances"],
    )

    semantic_ids = semantic_result.get("ids", [[]])[0]
    semantic_distances = semantic_result.get("distances", [[]])[0]

    semantic_ranks = {
        chunk_id: rank
        for rank, chunk_id in enumerate(semantic_ids, start=1)
    }

    distance_by_id = dict(zip(semantic_ids, semantic_distances))

    # Rank all matching chunks using BM25.
    lexical_scores = bm25_scores(query, documents)

    lexical_order = sorted(
        range(len(documents)),
        key=lambda index: lexical_scores[index],
        reverse=True,
    )

    lexical_ranks = {
        ids[index]: rank
        for rank, index in enumerate(
            [i for i in lexical_order if lexical_scores[i] > 0],
            start=1,
        )
    }

    # Reciprocal Rank Fusion combines both rankings.
    # It does not depend on any specific document or topic.
    rrf_constant = 60
    combined = {}

    for chunk_id in set(semantic_ranks) | set(lexical_ranks):
        score = 0.0

        if chunk_id in semantic_ranks:
            score += 1 / (rrf_constant + semantic_ranks[chunk_id])

        if chunk_id in lexical_ranks:
            score += 1 / (rrf_constant + lexical_ranks[chunk_id])

        combined[chunk_id] = score

    document_by_id = dict(zip(ids, documents))
    metadata_by_id = dict(zip(ids, metadatas))

    ranked_ids = sorted(
        combined,
        key=lambda chunk_id: combined[chunk_id],
        reverse=True,
    )

    matches = []

    for chunk_id in ranked_ids[:top_k]:
        metadata = metadata_by_id.get(chunk_id) or {}
        distance = distance_by_id.get(chunk_id)

        matches.append({
            "text": document_by_id[chunk_id],
            "filename": metadata.get("filename", "Unknown"),
            "page_number": metadata.get("page_number"),
            "chunk_index": metadata.get("chunk_index"),
            "distance": (
                round(float(distance), 4)
                if distance is not None
                else None
            ),
            "rerank_score": round(combined[chunk_id], 6),
        })

    return {
        "query": query,
        "results": matches,
    }
