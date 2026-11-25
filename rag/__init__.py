import logging

from .chain import build_rag_chain, chain_from_env, get_rag_response
from .retriever import ChromaRetriever
from .schemas import NOT_FOUND_ANSWER, RAGResponse

# rag.ingest is left out on purpose: importing it here would load it twice under python -m.
__all__ = [
    "NOT_FOUND_ANSWER",
    "ChromaRetriever",
    "RAGResponse",
    "build_rag_chain",
    "chain_from_env",
    "get_rag_response",
]

logging.getLogger(__name__).addHandler(logging.NullHandler())
