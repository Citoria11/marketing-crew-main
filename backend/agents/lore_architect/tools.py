"""ChromaDB RAG tool for the LoreArchitect agent."""
from __future__ import annotations

import os

CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "americana_lore")
CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))

_FALLBACK = (
    "An outlaw drifter rides the dusty Texas plains — boots worn thin, guitar "
    "held together with gaffer tape — haunted by lost love and the ghost of "
    "Johnny Cash echoing off canyon walls."
)


async def retrieve_lore_passages(query: str, top_k: int = 5) -> list[str]:
    """Query ChromaDB for semantically similar Americana/Outlaw passages.

    Returns a list of passage strings. If ChromaDB is unreachable or the
    collection is empty, returns a single fallback passage so downstream
    agents always have something to work with.
    """
    try:
        import chromadb
        from chromadb.utils import embedding_functions

        client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
        ef = embedding_functions.DefaultEmbeddingFunction()
        collection = client.get_or_create_collection(
            name=CHROMA_COLLECTION,
            embedding_function=ef,
        )
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            include=["documents"],
        )
        docs: list[str] = results.get("documents", [[]])[0]
        return docs if docs else [_FALLBACK]
    except Exception:  # noqa: BLE001
        return [_FALLBACK]
