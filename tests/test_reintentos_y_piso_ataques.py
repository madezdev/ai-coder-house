"""Ataques al piso opcional y a los dos niveles de reintento (devolución de la preentrega 2).

Los conteos usan el cliente del SDK que LangChain arma dentro de build_chat_model, copiado con
solo el transporte HTTP cambiado, así cuentan con el max_retries y el timeout de producción.
Ningún test llama a una API real ni lee .env: el transporte es httpx.MockTransport sobre un
host .invalid.
"""

import asyncio
import contextlib
import io
import logging
import re
import unittest
from collections.abc import Callable
from typing import Any
from unittest import mock

import httpx
from test_pipeline_edge_cases import (
    FAKE_KEY,
    LOGGER,
    VALID_ARGS,
    VALID_JSON,
    RoutingChatModel,
    anthropic_body,
    openai_body,
    tool_reply,
)

from entity_pipeline import (
    ProviderError,
    TruncatedOutputError,
    build_chain,
    demo,
    process_text,
)
from entity_pipeline.chain import REQUEST_TIMEOUT_SECONDS, build_chat_model
from unified_llm import ModelConfig

FLOOR_LOG = "Criticidad elevada"
PROVIDERS = ("openai", "anthropic")
BASE_URLS = {"openai": "http://mock.invalid/v1", "anthropic": "http://mock.invalid"}
Answer = Callable[[httpx.Request], httpx.Response]


def status(code: int) -> Answer:
    return lambda request: httpx.Response(code, json={"error": {"message": "down"}})


def read_timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ReadTimeout("timed out", request=request)


def connection_refused(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def cut(provider: str) -> Answer:
    if provider == "openai":
        body = openai_body("length", '{"tecnologias": ["Redis"], "nivel_de_crit')
    else:
        body = anthropic_body("max_tokens", VALID_ARGS)  # parses, so LangChain logs nothing
    return lambda request: httpx.Response(200, json=body)


def ok(provider: str) -> Answer:
    body = openai_body("tool_calls", VALID_JSON) if provider == "openai" else anthropic_body("tool_use", VALID_ARGS)
    return lambda request: httpx.Response(200, json=body)


TRANSPORT_FAILURES: dict[str, Answer] = {
    "503": status(503),
    "500": status(500),
    "529 overloaded": status(529),
    "429": status(429),
    "timeout de lectura": read_timeout,
    "conexión rechazada": connection_refused,
}


class ProductionClientCase(unittest.IsolatedAsyncioTestCase):
    def production_chain(self, provider: str, *answers: Answer, handler: Any = None):
        """Chain over the SDK client that build_chat_model creates, answered by ``answers`` in order.

        After the script ends, every extra request gets a valid answer: a request beyond the
        expected count would turn the failure into a success and show up in the assertions.
        """
        requests: list[httpx.Request] = []
        script = [*answers, ok(provider)]

        def scripted(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            return script[min(len(requests), len(script)) - 1](request)

        http = httpx.AsyncClient(transport=httpx.MockTransport(handler or scripted))
        self.addAsyncCleanup(http.aclose)
        config = ModelConfig(provider=provider, model="m", temperature=0, max_tokens=64)
        model = build_chat_model(config, FAKE_KEY)
        production = model.root_async_client if provider == "openai" else model._async_client
        client = production.copy(base_url=BASE_URLS[provider], http_client=http)
        # Only the length of the SDK backoff changes; the number of retries stays the production one.
        client._calculate_retry_timeout = lambda *args, **kwargs: 0.001
        if provider == "openai":
            model.root_async_client = client
            model.async_client = client.chat.completions
        else:
            model.__dict__["_async_client"] = client
        return build_chain(model, wait_between_attempts=False), requests, production


class ProductionClientConfigTests(ProductionClientCase):
    async def test_el_cliente_que_arma_build_chat_model_trae_2_reintentos_y_30_s(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                _, _, production = self.production_chain(provider)
                self.assertEqual(production.max_retries, 2)
                self.assertEqual(httpx.Timeout(production.timeout).read, REQUEST_TIMEOUT_SECONDS)


class TransportFailureCountTests(ProductionClientCase):
    async def test_cada_falla_de_transporte_cuesta_3_requests_y_un_solo_intento(self) -> None:
        for provider in PROVIDERS:
            for label, failure in TRANSPORT_FAILURES.items():
                with self.subTest(provider=provider, falla=label):
                    chain, requests, _ = self.production_chain(provider, failure, failure, failure)
                    with self.assertLogs(LOGGER, level="INFO") as logs, self.assertRaises(ProviderError):
                        await process_text("ERROR redis", chain=chain)
                    self.assertEqual(len(requests), 3)
                    self.assertEqual(sum("Intento" in line for line in logs.output), 1)

    async def test_timeouts_y_conexion_quedan_como_network_reintentable(self) -> None:
        for provider in PROVIDERS:
            for failure in (read_timeout, connection_refused):
                with self.subTest(provider=provider, falla=failure.__name__):
                    chain, _, _ = self.production_chain(provider, failure, failure, failure)
                    with self.assertRaises(ProviderError) as caught:
                        await process_text("ERROR redis", chain=chain)
                    self.assertEqual((caught.exception.code, caught.exception.retryable), ("network", True))

    async def test_una_caida_en_el_reintento_de_with_retry_no_relanza_la_cadena(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                down = status(503)
                chain, requests, _ = self.production_chain(provider, cut(provider), down, down, down)
                with self.assertLogs(LOGGER, level="INFO") as logs, self.assertRaises(ProviderError):
                    await process_text("ERROR redis", chain=chain)
                self.assertEqual(len(requests), 4)
                self.assertTrue(any("Intento 2" in line for line in logs.output))
                self.assertFalse(any("Intento 3" in line for line in logs.output))


class WorstCaseCountTests(ProductionClientCase):
    async def test_peor_caso_con_fallas_mezcladas_no_pasa_de_9_requests(self) -> None:
        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                attempts = (
                    (status(503), status(503), cut(provider)),
                    (read_timeout, status(429), cut(provider)),
                    (connection_refused, status(529), cut(provider)),
                )
                chain, requests, _ = self.production_chain(provider, *(a for att in attempts for a in att))
                with self.assertRaises(TruncatedOutputError):
                    await process_text("ERROR redis", chain=chain)
                self.assertEqual(len(requests), 9)

    async def test_asyncio_timeout_corta_el_pedido_como_dice_el_readme(self) -> None:
        async def stalled(request: httpx.Request) -> httpx.Response:
            await asyncio.sleep(5)
            return httpx.Response(503)

        for provider in PROVIDERS:
            with self.subTest(provider=provider):
                chain, _, _ = self.production_chain(provider, handler=stalled)
                with self.assertRaises(TimeoutError):
                    async with asyncio.timeout(0.2):
                        await process_text("ERROR redis", chain=chain)


def floor_model() -> RoutingChatModel:
    baja = tool_reply({**VALID_ARGS, "nivel_de_criticidad": "baja"})
    return RoutingChatModel(routes={"pod": baja})


class SharedChainFloorTests(unittest.IsolatedAsyncioTestCase):
    async def test_cadena_compartida_aplica_el_piso_solo_a_quien_lo_pidio(self) -> None:
        chain = build_chain(floor_model(), wait_between_attempts=False)
        flags = (True, False, True, False)
        texts = [f"pod {'x' * i} en CrashLoopBackOff" for i in range(len(flags))]
        with self.assertLogs(LOGGER, level="INFO") as logs:
            results = await asyncio.gather(
                *(process_text(t, chain=chain, apply_floor=f) for t, f in zip(texts, flags, strict=True))
            )
        self.assertEqual([r.nivel_de_criticidad for r in results], ["alta", "baja", "alta", "baja"])
        flag_by_id: dict[str, bool] = {}
        floored_ids: list[str] = []
        for line in logs.output:
            request_id = re.search(r"\[([0-9a-f]{8})\]", line).group(1)
            if size := re.search(r"Procesando texto de (\d+) caracteres", line):
                flag_by_id[request_id] = flags[[len(t) for t in texts].index(int(size.group(1)))]
            if FLOOR_LOG in line:
                floored_ids.append(request_id)
        self.assertEqual(len(floored_ids), 2)
        self.assertTrue(all(flag_by_id[i] for i in floored_ids), (flag_by_id, floored_ids))


class DemoFloorFlagTests(unittest.TestCase):
    SIGNAL_TEXT = "pod payments en CrashLoopBackOff"

    def run_demo_main(self, *argv: str) -> str:
        chain = build_chain(floor_model(), wait_between_attempts=False)
        httpx_logger = logging.getLogger("httpx")
        self.addCleanup(httpx_logger.setLevel, httpx_logger.level)
        out = io.StringIO()
        with (
            mock.patch("sys.argv", ["entity_pipeline.demo", *argv]),
            mock.patch.object(demo, "chain_from_env", return_value=chain),
            mock.patch.object(logging, "basicConfig"),
            contextlib.redirect_stdout(out),
            self.assertLogs(LOGGER, level="INFO"),
            self.assertRaises(SystemExit) as exited,
        ):
            demo.main()
        self.assertEqual(exited.exception.code, 0, out.getvalue())
        return out.getvalue()

    def test_demo_con_piso_antes_del_texto_eleva_la_criticidad(self) -> None:
        self.assertIn('"nivel_de_criticidad": "alta"', self.run_demo_main("--piso", self.SIGNAL_TEXT))

    def test_demo_con_piso_despues_del_texto_eleva_la_criticidad(self) -> None:
        self.assertIn('"nivel_de_criticidad": "alta"', self.run_demo_main(self.SIGNAL_TEXT, "--piso"))

    def test_demo_sin_piso_respeta_lo_que_devolvio_el_modelo(self) -> None:
        self.assertIn('"nivel_de_criticidad": "baja"', self.run_demo_main(self.SIGNAL_TEXT))


if __name__ == "__main__":
    unittest.main()
