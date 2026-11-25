import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

import tiktoken
from chromadb.api.client import SharedSystemClient
from langchain_core.embeddings import Embeddings
from langchain_core.exceptions import OutputParserException
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, BaseMessage
from pydantic import Field, ValidationError

from rag import NOT_FOUND_ANSWER, ChromaRetriever, build_rag_chain, get_rag_response
from rag.chain import chain_from_env
from rag.ingest import build_splitter, ingest, load_documents, split_documents
from rag.settings import CHUNK_SIZE, DATA_DIR
from rag.store import open_client, open_collection

ENCODING = tiktoken.get_encoding("cl100k_base")
KEYWORDS = ("guardia", "despliegue", "respaldo", "incidente", "postgresql", "canary")


class KeywordEmbeddings(Embeddings):
    """Counts a few keywords, so the closest chunk is predictable without calling an API."""

    def __init__(self, model: str = "keywords-v1", fail: bool = False) -> None:
        self.model = model
        self.fail = fail
        self.embedded = 0

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self.fail:
            raise RuntimeError("API caída")
        self.embedded += len(texts)
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        # The small constant avoids a zero vector, which has no cosine distance.
        return [lowered.count(keyword) + 0.01 for keyword in KEYWORDS]


class RecordingModel(GenericFakeChatModel):
    """Replies with the queued messages and keeps the prompts it received."""

    prompts: list[list[BaseMessage]] = Field(default_factory=list)

    def _generate(self, messages: list[BaseMessage], *args: Any, **kwargs: Any) -> Any:
        self.prompts.append(messages)
        return super()._generate(messages, *args, **kwargs)


def model_replying(*contents: str) -> RecordingModel:
    return RecordingModel(messages=iter(AIMessage(content=content) for content in contents))


class VectorstoreTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = Path(tempfile.mkdtemp())
        self.data_dir = self.tmp / "data"
        shutil.copytree(DATA_DIR, self.data_dir)
        self.store_dir = self.tmp / "vectorstore"
        self.client = open_client(self.store_dir)
        self.embeddings = KeywordEmbeddings()

    def tearDown(self) -> None:
        SharedSystemClient.clear_system_cache()
        shutil.rmtree(self.tmp, ignore_errors=True)

    def ingest(self, **kwargs: Any):
        options = {"client": self.client, "embeddings": self.embeddings, **kwargs}
        return ingest(self.data_dir, **options)


class SplitTests(unittest.TestCase):
    def test_dataset_chunks_fit_the_token_budget(self) -> None:
        documents = load_documents()
        chunks = split_documents(documents)

        self.assertGreaterEqual(len(documents), 3)
        self.assertTrue(all(len(ENCODING.encode(c.page_content)) <= CHUNK_SIZE for c in chunks))
        self.assertEqual(len({chunk.id for chunk in chunks}), len(chunks))
        for document in documents:
            source = document.metadata["fuente"]
            own = [chunk for chunk in chunks if chunk.metadata["fuente"] == source]
            self.assertGreaterEqual(len(own), 2, source)
            self.assertEqual(own[0].id, f"{source}#0")
            self.assertTrue(own[0].metadata["titulo"])

    def test_chunks_start_at_markdown_headings(self) -> None:
        chunks = split_documents(load_documents())

        self.assertTrue(all(chunk.page_content.startswith("#") for chunk in chunks))

    def test_long_section_is_cut_with_overlap(self) -> None:
        text = " ".join(f"Paso {i}: revisar el servicio {i}." for i in range(300))
        document = load_documents_from(self, {"largo.md": text})[0]

        chunks = split_documents([document], build_splitter())

        self.assertGreaterEqual(len(chunks), 3)
        for previous, current in zip(chunks, chunks[1:]):
            self.assertLessEqual(len(ENCODING.encode(previous.page_content)), CHUNK_SIZE)
            opening = " ".join(current.page_content.split()[:6])
            self.assertIn(opening, previous.page_content)

    def test_only_md_and_txt_files_are_loaded(self) -> None:
        documents = load_documents_from(
            self, {"a.md": "# A\n\nuno", "b.txt": "dos", "c.pdf": "tres", "d.json": "{}"}
        )

        self.assertEqual([doc.metadata["fuente"] for doc in documents], ["a.md", "b.txt"])
        self.assertEqual([doc.metadata["titulo"] for doc in documents], ["A", "b"])

    def test_folder_without_documents_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "No hay archivos"):
            load_documents_from(self, {"notas.pdf": "nada"})


def load_documents_from(test: unittest.TestCase, files: dict[str, str]):
    folder = Path(tempfile.mkdtemp())
    test.addCleanup(shutil.rmtree, folder, True)
    for name, content in files.items():
        (folder / name).write_text(content, encoding="utf-8")
    return load_documents(folder)


class IngestTests(VectorstoreTestCase):
    def test_second_run_does_not_reindex(self) -> None:
        first = self.ingest()
        embedded = self.embeddings.embedded

        second = self.ingest()

        self.assertTrue(first.reindexed)
        self.assertFalse(second.reindexed)
        self.assertEqual(self.embeddings.embedded, embedded)
        self.assertEqual(second.chunks, first.chunks)
        self.assertEqual(open_collection(self.client).count(), first.chunks)

    def test_index_survives_a_new_client(self) -> None:
        first = self.ingest()
        SharedSystemClient.clear_system_cache()

        reopened = open_client(self.store_dir)

        collection = open_collection(reopened)
        self.assertEqual(collection.count(), first.chunks)
        self.assertEqual(collection.metadata["embedding_model"], "keywords-v1")
        again = ingest(self.data_dir, client=reopened, embeddings=self.embeddings)
        self.assertFalse(again.reindexed)

    def test_changed_file_triggers_reindex(self) -> None:
        self.ingest()
        path = self.data_dir / "despliegues.md"
        path.write_text(path.read_text(encoding="utf-8") + "\nNueva regla.\n", encoding="utf-8")

        self.assertTrue(self.ingest().reindexed)

    def test_other_embedding_model_triggers_reindex(self) -> None:
        self.ingest()
        other = KeywordEmbeddings(model="keywords-v2")

        result = ingest(self.data_dir, client=self.client, embeddings=other)

        self.assertTrue(result.reindexed)
        self.assertEqual(open_collection(self.client).metadata["embedding_model"], "keywords-v2")

    def test_rebuild_forces_reindex(self) -> None:
        self.ingest()

        self.assertTrue(self.ingest(rebuild=True).reindexed)

    def test_failed_embedding_keeps_previous_index(self) -> None:
        first = self.ingest()
        (self.data_dir / "extra.md").write_text("# Extra\n\nTexto nuevo.", encoding="utf-8")

        with self.assertRaises(RuntimeError):
            self.ingest(embeddings=KeywordEmbeddings(fail=True))

        self.assertEqual(open_collection(self.client).count(), first.chunks)
        self.assertTrue(self.ingest().reindexed)


class RetrieverTests(VectorstoreTestCase, unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ingest()

    async def test_returns_the_closest_chunks_up_to_top_k(self) -> None:
        retriever = ChromaRetriever(client=self.client, embeddings=self.embeddings, top_k=3)

        documents = await retriever.ainvoke("¿Cuánto dura el canary de un despliegue?")

        self.assertEqual(len(documents), 3)
        self.assertEqual(documents[0].id, "despliegues.md#1")
        distances = [doc.metadata["distancia"] for doc in documents]
        self.assertEqual(distances, sorted(distances))

    def test_sync_search_matches_async(self) -> None:
        retriever = ChromaRetriever(client=self.client, embeddings=self.embeddings)

        documents = retriever.invoke("respaldo de PostgreSQL")

        self.assertEqual(documents[0].metadata["fuente"], "respaldos_y_recuperacion.md")

    def test_refuses_another_embedding_model(self) -> None:
        other = KeywordEmbeddings(model="otro-modelo")
        retriever = ChromaRetriever(client=self.client, embeddings=other)

        with self.assertRaisesRegex(ValueError, "keywords-v1.*otro-modelo"):
            retriever.invoke("respaldo de PostgreSQL")

    def test_top_k_is_capped(self) -> None:
        with self.assertRaises(ValidationError):
            ChromaRetriever(client=self.client, embeddings=self.embeddings, top_k=6)


class ChainTests(VectorstoreTestCase, unittest.IsolatedAsyncioTestCase):
    QUESTION = "¿Cuánto dura el canary de un despliegue?"

    def setUp(self) -> None:
        super().setUp()
        self.ingest()
        self.retriever = ChromaRetriever(client=self.client, embeddings=self.embeddings, top_k=3)

    async def ask(self, *replies: str, question: str = QUESTION):
        self.model = model_replying(*replies)
        chain = build_rag_chain(self.retriever, self.model)
        return await get_rag_response(question, chain=chain)

    async def test_reply_is_parsed_and_invented_references_dropped(self) -> None:
        reply = (
            '{"respuesta": "El canary recibe el 5 % del tráfico durante 30 minutos.", '
            '"referencias": ["despliegues.md#1", "[despliegues.md#1]", "inventado.md#9"]}'
        )

        with self.assertLogs("rag.chain", "WARNING") as logs:
            result = await self.ask(reply)

        self.assertTrue(result.answered)
        self.assertEqual(result.referencias, ["despliegues.md#1"])
        self.assertIn("inventado.md#9", logs.output[0])

    async def test_prompt_has_the_question_and_only_top_k_chunks(self) -> None:
        await self.ask('{"respuesta": "30 minutos.", "referencias": ["despliegues.md#1"]}')

        system, human = self.model.prompts[0]
        self.assertIn("No lo sé", system.content)
        self.assertIn('"referencias"', system.content)
        self.assertEqual(human.content.count("<fragmento "), 3)
        opening = '<fragmento id="despliegues.md#1" documento="Política de despliegues">'
        self.assertIn(opening, human.content)
        self.assertTrue(human.content.endswith(f"PREGUNTA: {self.QUESTION}"))

    async def test_unknown_answer_has_no_references(self) -> None:
        reply = '{"respuesta": "No lo sé. El contexto no lo menciona.", "referencias": ["x.md#0"]}'

        result = await self.ask(reply, question="¿En qué año se lanzó PostgreSQL?")

        self.assertFalse(result.answered)
        self.assertEqual(result.respuesta, NOT_FOUND_ANSWER)
        self.assertEqual(result.referencias, [])

    async def test_json_inside_a_code_fence_is_accepted(self) -> None:
        result = await self.ask(
            '```json\n{"respuesta": "30 minutos.", "referencias": ["despliegues.md#1"]}\n```'
        )

        self.assertEqual(result.respuesta, "30 minutos.")

    async def test_reply_outside_the_schema_raises(self) -> None:
        for reply in ("El canary dura 30 minutos.", '{"respuesta": "", "referencias": []}'):
            with self.subTest(reply=reply), self.assertRaises(OutputParserException):
                await self.ask(reply)

    async def test_invalid_query_does_not_call_the_model(self) -> None:
        model = model_replying("{}")
        chain = build_rag_chain(self.retriever, model)
        cases = [("   ", ValueError), ("¿?", ValueError), ("x" * 1001, ValueError)]
        for query, error in [*cases, (None, TypeError)]:
            with self.subTest(query=query), self.assertRaises(error):
                await get_rag_response(query, chain=chain)
        self.assertEqual(model.prompts, [])

    def test_missing_vectorstore_asks_for_ingestion(self) -> None:
        missing = self.tmp / "sin_indexar"

        with self.assertRaisesRegex(ValueError, "rag.ingest"):
            chain_from_env(self.tmp / ".env", missing)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
