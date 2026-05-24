"""ChromaDB client singleton — connects to ChromaDB server via HTTP.

In development, ChromaDB runs as a Docker service (chromadb/chroma image).
In the old CampusMind, we used PersistentClient (embedded mode) which caused
file-locking conflicts between FastAPI and Celery. Server mode fixes this.
"""

import os
import chromadb
from chromadb.api.models.Collection import Collection

CHROMA_HOST = os.getenv("CHROMA_HOST", "localhost")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8100"))
COLLECTION_NAME = "campus_vectors"

chroma_client: chromadb.ClientAPI = None  # type: ignore[assignment]
campus_collection: Collection = None  # type: ignore[assignment]


def connect_chroma() -> None:
    """Connect to ChromaDB server and get or create the collection."""
    global chroma_client, campus_collection
    chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)
    campus_collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_chroma_collection() -> Collection:
    """Return the current campus_vectors collection handle."""
    return campus_collection
