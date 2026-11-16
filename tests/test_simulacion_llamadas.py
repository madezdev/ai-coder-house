import asyncio
import contextlib
import io
import time
import unittest

from ejercicios.llamadas_async.simulacion_llamadas import (
    ejecutar_con_semaforo,
    ejecutar_con_timeout_total,
)


def llamada_simulada(segundos: float):
    # Llamada falsa con latencia corta para que las pruebas corran rápido
    async def llamada(prompt: str) -> dict:
        await asyncio.sleep(segundos)
        return {"respuesta": f"ok en {segundos} s"}

    return llamada


class LlamadasAsyncTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        # El ejercicio imprime su log en stdout; se descarta para no ensuciar la salida de unittest
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    async def test_calls_run_concurrently(self) -> None:
        llamadas = {"a": llamada_simulada(0.1), "b": llamada_simulada(0.2), "c": llamada_simulada(0.3)}

        inicio = time.perf_counter()
        resultados = await ejecutar_con_timeout_total(llamadas, "hola", timeout=1.0)
        duracion = time.perf_counter() - inicio

        self.assertTrue(all(r is not None for r in resultados.values()))
        # En serie tardarían 0.6 s; en paralelo, lo que tarda la más lenta (0.3 s)
        self.assertLess(duracion, 0.45)

    async def test_total_timeout_cancels_the_slow_call_and_keeps_the_rest(self) -> None:
        llamadas = {"rapida": llamada_simulada(0.05), "lenta": llamada_simulada(1.0)}

        resultados = await ejecutar_con_timeout_total(llamadas, "hola", timeout=0.2)

        self.assertEqual(resultados["rapida"], {"respuesta": "ok en 0.05 s"})
        self.assertIsNone(resultados["lenta"])

    async def test_semaphore_limits_concurrency(self) -> None:
        activas = 0
        maximo = 0

        async def llamada_contada(prompt: str) -> dict:
            nonlocal activas, maximo
            activas += 1
            maximo = max(maximo, activas)
            await asyncio.sleep(0.05)
            activas -= 1
            return {"respuesta": "ok"}

        llamadas = [(f"#{i}", llamada_contada) for i in range(10)]
        resultados = await ejecutar_con_semaforo(llamadas, "hola", max_concurrencia=2, timeout_por_llamada=1.0)

        self.assertEqual(len(resultados), 10)
        self.assertEqual(maximo, 2)

    async def test_per_call_timeout_does_not_affect_the_others(self) -> None:
        llamadas = [("lenta", llamada_simulada(1.0)), ("rapida", llamada_simulada(0.05))]

        resultados = await ejecutar_con_semaforo(llamadas, "hola", max_concurrencia=2, timeout_por_llamada=0.2)

        self.assertIsInstance(resultados[0], TimeoutError)
        self.assertEqual(resultados[1], {"respuesta": "ok en 0.05 s"})

    async def test_queue_time_does_not_count_toward_the_timeout(self) -> None:
        # Con un solo lugar, la segunda espera 0.15 s en cola y luego corre 0.15 s:
        # termina a los 0.30 s, pero su timeout de 0.2 s empieza al conseguir lugar
        llamadas = [("primera", llamada_simulada(0.15)), ("segunda", llamada_simulada(0.15))]

        resultados = await ejecutar_con_semaforo(llamadas, "hola", max_concurrencia=1, timeout_por_llamada=0.2)

        self.assertFalse(any(isinstance(r, Exception) for r in resultados))
