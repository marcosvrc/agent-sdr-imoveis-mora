from typing import Protocol


class Embedder(Protocol):
    dimensoes: int
    def embed(self, texto: str) -> list[float]: ...
