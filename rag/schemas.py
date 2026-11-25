"""Output contract of the RAG chain."""

import unicodedata

from pydantic import BaseModel, Field, field_validator

NOT_FOUND_ANSWER = "No lo sé"


def _plain(text: str) -> str:
    """Lowercase, without accents and without leading quotes or punctuation."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    letters = "".join(char for char in decomposed if not unicodedata.combining(char))
    return letters.lstrip(" \t\n\"'«“‘¿¡*_-.,:")


class RAGResponse(BaseModel):
    respuesta: str = Field(
        min_length=1,
        description='Respuesta basada solo en el contexto, o exactamente "No lo sé"',
    )
    referencias: list[str] = Field(
        default_factory=list,
        description=(
            'Ids de los fragmentos usados, por ejemplo "despliegues.md#1"; '
            'lista vacía si la respuesta es "No lo sé"'
        ),
    )

    @field_validator("respuesta")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        if not (value := value.strip()):
            raise ValueError("la respuesta está vacía")
        return value

    @field_validator("referencias", mode="before")
    @classmethod
    def null_as_empty(cls, value: object) -> object:
        return [] if value is None else value

    @property
    def answered(self) -> bool:
        return not _plain(self.respuesta).startswith(_plain(NOT_FOUND_ANSWER))
