"""Ingestion: reads data/, splits the files into token-sized chunks and stores them in ChromaDB.

``python -m rag.ingest`` does nothing when the collection already holds the current files.
"""

import argparse
import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path

from chromadb.api import ClientAPI
from chromadb.errors import ChromaError
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

from .settings import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    COLLECTION_NAME,
    DATA_DIR,
    VECTORSTORE_DIR,
    embedding_model_name,
    embeddings_from_env,
)
from .store import open_client, open_collection

logger = logging.getLogger(__name__)

SUPPORTED_SUFFIXES = frozenset({".md", ".txt"})
# Encoding of OpenAI's embedding models, so a 500-token chunk is 500 tokens for the model too.
TOKEN_ENCODING = "cl100k_base"


@dataclass(frozen=True)
class IngestResult:
    files: int
    chunks: int
    reindexed: bool


def load_documents(data_dir: Path = DATA_DIR) -> list[Document]:
    # Hidden files include the ._name.md copies that macOS leaves on external drives.
    paths = sorted(
        path
        for path in data_dir.glob("*")
        if path.is_file()
        and path.suffix.lower() in SUPPORTED_SUFFIXES
        and not path.name.startswith(".")
    )
    documents = []
    for path in paths:
        text = _read_text(path)
        if not text.strip():
            logger.warning("Se omite %s: está vacío", path.name)
            continue
        metadata = {"fuente": path.name, "titulo": _title(text) or path.stem}
        documents.append(Document(page_content=text, metadata=metadata))
    if not documents:
        raise ValueError(f"No hay archivos .md ni .txt con texto en {data_dir}")
    return documents


def _read_text(path: Path) -> str:
    try:
        # utf-8-sig drops the BOM some editors add, which would otherwise hide the title.
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path.name} no está en UTF-8") from exc


def _title(text: str) -> str:
    for line in text.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def build_splitter(
    chunk_size: int = CHUNK_SIZE, chunk_overlap: int = CHUNK_OVERLAP
) -> RecursiveCharacterTextSplitter:
    """Counts tokens and cuts at Markdown headings first, then paragraphs, lines and words."""
    return RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        encoding_name=TOKEN_ENCODING,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=RecursiveCharacterTextSplitter.get_separators_for_language(Language.MARKDOWN),
        is_separator_regex=True,
        # A document that mentions <|endoftext|> is plain text, not a special token.
        disallowed_special=(),
    )


def split_documents(
    documents: list[Document], splitter: RecursiveCharacterTextSplitter | None = None
) -> list[Document]:
    splitter = splitter or build_splitter()
    chunks = []
    for document in documents:
        for index, chunk in enumerate(splitter.split_documents([document])):
            chunk.id = f"{chunk.metadata['fuente']}#{index}"
            chunk.metadata["fragmento"] = index
            chunks.append(chunk)
    return chunks


def fingerprint(documents: list[Document], embedding_model: str) -> str:
    """Changes when a file, the chunking parameters or the embedding model change."""
    digest = hashlib.sha256(f"{embedding_model}|{CHUNK_SIZE}|{CHUNK_OVERLAP}".encode())
    for document in documents:
        for part in (document.metadata["fuente"], document.page_content):
            digest.update(part.encode())
            digest.update(b"\0")
    return digest.hexdigest()


def ingest(
    data_dir: Path = DATA_DIR,
    *,
    client: ClientAPI | None = None,
    embeddings: Embeddings | None = None,
    collection_name: str = COLLECTION_NAME,
    rebuild: bool = False,
) -> IngestResult:
    """Index the files in ``data_dir`` unless the collection already holds exactly these files."""
    documents = load_documents(data_dir)
    embeddings = embeddings or embeddings_from_env()
    client = client or open_client()
    model = embedding_model_name(embeddings)
    signature = fingerprint(documents, model)

    current = open_collection(client, collection_name)
    if current is not None and not rebuild:
        stored = (current.metadata or {}).get("fingerprint")
        if stored == signature and (count := current.count()):
            logger.info("La colección ya está al día (%d fragmentos); no se reindexa", count)
            return IngestResult(len(documents), count, reindexed=False)

    chunks = split_documents(documents)
    vectors = embeddings.embed_documents([chunk.page_content for chunk in chunks])
    if len(vectors) != len(chunks):
        raise ValueError(f"Se pidieron {len(chunks)} embeddings y llegaron {len(vectors)}")
    metadata = {
        "embedding_model": model,
        "fingerprint": signature,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }
    _replace_collection(client, collection_name, chunks, vectors, metadata)
    logger.info("Indexados %d fragmentos de %d archivos con %s", len(chunks), len(documents), model)
    return IngestResult(len(documents), len(chunks), reindexed=True)


def _replace_collection(
    client: ClientAPI,
    name: str,
    chunks: list[Document],
    vectors: list[list[float]],
    metadata: dict[str, str | int],
) -> None:
    """Fill a staging collection and swap it in only when every chunk was stored.

    If anything fails before the swap, the previous index stays untouched.
    """
    staging = f"{name}-staging"
    if open_collection(client, staging) is not None:
        client.delete_collection(staging)
    collection = client.create_collection(
        staging,
        configuration={"hnsw": {"space": "cosine"}},
        metadata=metadata,
        embedding_function=None,
    )
    try:
        batch_size = client.get_max_batch_size()
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            collection.add(
                ids=[chunk.id for chunk in batch],
                embeddings=vectors[start : start + batch_size],
                documents=[chunk.page_content for chunk in batch],
                metadatas=[chunk.metadata for chunk in batch],
            )
    except Exception:
        client.delete_collection(staging)
        raise
    if open_collection(client, name) is not None:
        client.delete_collection(name)
    collection.modify(name=name)


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)-7s %(message)s", datefmt="%H:%M:%S"
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


def main() -> None:
    parser = argparse.ArgumentParser(description="Indexa los documentos de data/ en ChromaDB.")
    parser.add_argument(
        "--rebuild", action="store_true", help="Reindexa aunque la colección esté al día."
    )
    args = parser.parse_args()
    configure_logging()
    try:
        result = ingest(rebuild=args.rebuild)
    except (ValueError, ChromaError) as exc:
        raise SystemExit(f"No se pudo indexar: {exc}") from exc
    state = "indexados" if result.reindexed else "ya estaban indexados"
    print(f"{result.chunks} fragmentos de {result.files} archivos {state} en {VECTORSTORE_DIR}")


if __name__ == "__main__":
    main()
