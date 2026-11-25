"""Paths, chunking parameters and the embedding model shared by ingestion and queries."""

from pathlib import Path

from dotenv import dotenv_values
from langchain_core.embeddings import Embeddings
from langchain_openai import OpenAIEmbeddings

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
DATA_DIR = ROOT / "data"
VECTORSTORE_DIR = ROOT / "vectorstore"
COLLECTION_NAME = "manuales_plataforma"
DEFAULT_EMBEDDING_MODEL = "text-embedding-3-small"
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
TOP_K = 4


def embeddings_from_env(path: Path = ENV_PATH) -> OpenAIEmbeddings:
    """The single embedding model used to index and to query, read from the local .env.

    Anthropic has no embeddings API, so OPENAI_API_KEY is required whatever LLM_PROVIDER says.
    """
    if not path.is_file():
        raise ValueError(f"Falta {path.name}; copia .env.example y agrega tu clave")
    values = dotenv_values(path)
    api_key = values.get("OPENAI_API_KEY")
    if not api_key:
        raise ValueError("Los embeddings usan OpenAI: falta OPENAI_API_KEY en .env")
    model = values.get("EMBEDDING_MODEL") or DEFAULT_EMBEDDING_MODEL
    return OpenAIEmbeddings(model=model, api_key=api_key, timeout=30, max_retries=2)


def embedding_model_name(embeddings: Embeddings) -> str:
    return getattr(embeddings, "model", None) or type(embeddings).__name__
