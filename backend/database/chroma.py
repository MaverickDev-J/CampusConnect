"""ChromaDB persistent client singleton."""

import chromadb
from chromadb.api.models.Collection import Collection

CHROMA_PATH = "./chroma_data"
COLLECTION_NAME = "campus_vectors"

chroma_client: chromadb.ClientAPI = None  # type: ignore[assignment]
campus_collection: Collection = None  # type: ignore[assignment]


def connect_chroma() -> None:
    """Initialise the PersistentClient and get or create the collection."""
    global chroma_client, campus_collection
    chroma_client = chromadb.PersistentClient(path=CHROMA_PATH)
    campus_collection = chroma_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def get_chroma_collection() -> Collection:
    """Return the current campus_vectors collection handle."""
    return campus_collection
