"""Runs the two checks: a question the manuals answer and a trap question they do not."""

import argparse
import asyncio

import anthropic
import openai
from chromadb.errors import ChromaError
from langchain_core.exceptions import OutputParserException

from .chain import get_rag_response
from .ingest import configure_logging, ingest
from .schemas import NOT_FOUND_ANSWER

# (label, question, whether the manuals contain the answer)
CHECKS = [
    (
        "pregunta con respuesta en los documentos",
        "¿Cuánto tiempo tiene la guardia primaria para acusar recibo de una alerta P1 "
        "y qué pasa si no lo hace?",
        True,
    ),
    (
        "pregunta trampa",
        "¿En qué año se lanzó la primera versión de PostgreSQL?",
        False,
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Consulta los manuales indexados en ChromaDB.")
    parser.add_argument(
        "pregunta", nargs="?", help="Pregunta propia; sin ella se corren las dos pruebas."
    )
    return parser.parse_args()


async def run(checks: list[tuple[str, str, bool | None]]) -> int:
    results = await asyncio.gather(
        *(get_rag_response(question) for _, question, _ in checks), return_exceptions=True
    )
    failures = 0
    for (label, question, expected), result in zip(checks, results, strict=True):
        print(f"\n### {label}\n{question}")
        if isinstance(result, OutputParserException):
            failures += 1
            print(f"Respuesta inválida: {result}")
            continue
        if isinstance(result, BaseException):
            raise result
        print(result.model_dump_json(indent=2))
        if expected is None:
            continue
        if result.answered == expected:
            print("Resultado: OK")
        else:
            failures += 1
            wanted = "una respuesta con referencias" if expected else f'"{NOT_FOUND_ANSWER}"'
            print(f"Resultado: FALLA, se esperaba {wanted}")
    return failures


def main() -> None:
    args = parse_args()
    configure_logging()
    checks = [("pregunta recibida", args.pregunta, None)] if args.pregunta else CHECKS
    try:
        ingest()
        failures = asyncio.run(run(checks))
    except (ValueError, ChromaError) as exc:
        raise SystemExit(f"Configuración inválida: {exc}") from exc
    except (openai.APIError, anthropic.APIError) as exc:
        raise SystemExit(f"Error del proveedor: {exc}") from exc
    raise SystemExit(1 if failures else 0)


if __name__ == "__main__":
    main()
