"""Access to the local ChromaDB, shared by ingestion and queries."""

from pathlib import Path

import chromadb
from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from chromadb.config import Settings
from chromadb.errors import ChromaError, NotFoundError

from .settings import COLLECTION_NAME, VECTORSTORE_DIR


def open_client(path: Path = VECTORSTORE_DIR) -> ClientAPI:
    try:
        return chromadb.PersistentClient(
            path=str(path), settings=Settings(anonymized_telemetry=False)
        )
    except ChromaError as exc:
        raise ValueError(
            f"No se pudo abrir la base en {path} ({exc}); bórrala y vuelve a correr la ingesta"
        ) from exc


def open_collection(client: ClientAPI, name: str = COLLECTION_NAME) -> Collection | None:
    try:
        # Without an embedding function Chroma never embeds on its own: every vector comes from us.
        return client.get_collection(name, embedding_function=None)
    except NotFoundError:
        return None


def require_collection(client: ClientAPI, name: str = COLLECTION_NAME) -> Collection:
    collection = open_collection(client, name)
    if collection is None or not collection.count():
        raise ValueError("No hay base vectorial; corre primero python -m rag.ingest")
    return collection
