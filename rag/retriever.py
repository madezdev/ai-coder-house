"""Retriever: embeds the question with the indexing model and returns the closest chunks."""

import asyncio
import logging

from chromadb.api import ClientAPI
from chromadb.api.models.Collection import Collection
from langchain_core.callbacks import (
    AsyncCallbackManagerForRetrieverRun,
    CallbackManagerForRetrieverRun,
)
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.retrievers import BaseRetriever
from pydantic import ConfigDict, Field

from .settings import COLLECTION_NAME, TOP_K, embedding_model_name
from .store import require_collection

logger = logging.getLogger(__name__)

MIN_TOP_K = 3
MAX_TOP_K = 5


class ChromaRetriever(BaseRetriever):
    client: ClientAPI
    embeddings: Embeddings
    collection_name: str = COLLECTION_NAME
    top_k: int = Field(default=TOP_K, ge=MIN_TOP_K, le=MAX_TOP_K)

    model_config = ConfigDict(arbitrary_types_allowed=True)

    def get_collection(self) -> Collection:
        """Opened on every query, so a reindex in the same process is picked up.

        Refuses to query with a model other than the one that built the index: vectors from
        different models live in different spaces, so the distances would be noise.
        """
        collection = require_collection(self.client, self.collection_name)
        indexed = (collection.metadata or {}).get("embedding_model")
        current = embedding_model_name(self.embeddings)
        if indexed != current:
            raise ValueError(
                f"La colección se indexó con {indexed} y la consulta usaría {current}; "
                "vuelve a correr python -m rag.ingest --rebuild"
            )
        return collection

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> list[Document]:
        return self._search(query, self.embeddings.embed_query(query))

    async def _aget_relevant_documents(
        self, query: str, *, run_manager: AsyncCallbackManagerForRetrieverRun
    ) -> list[Document]:
        vector = await self.embeddings.aembed_query(query)
        # The Chroma client is synchronous; the thread keeps the event loop free.
        return await asyncio.to_thread(self._search, query, vector)

    def _search(self, query: str, vector: list[float]) -> list[Document]:
        result = self.get_collection().query(
            query_embeddings=[vector],
            n_results=self.top_k,
            include=["documents", "metadatas", "distances"],
        )
        documents = [
            Document(id=chunk_id, page_content=text, metadata={**metadata, "distancia": distance})
            for chunk_id, text, metadata, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
                strict=True,
            )
        ]
        logger.info(
            "Fragmentos para %r: %s",
            query[:60],
            ", ".join(f"{doc.id} ({doc.metadata['distancia']:.3f})" for doc in documents),
        )
        return documents
