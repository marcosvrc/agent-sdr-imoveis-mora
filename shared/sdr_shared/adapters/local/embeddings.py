"""Embeddings locais via Ollama (ex.: nomic-embed-text = 768 dims, bge-m3 = 1024 dims, multilíngue)."""
import httpx


class OllamaEmbedder:
    def __init__(self, url: str, model: str):
        self._url, self._model = url, model
        self.dimensoes = 1024 if "bge-m3" in model else 768
        # Um cliente por instância, e a instância vive o processo inteiro (ver `get_embedder`):
        # `httpx.post` solto abria e fechava uma conexão TCP por embedding — handshake a cada busca,
        # a cada reindexação de imóvel, a cada pergunta institucional. Com o cliente persistente a
        # conexão fica no pool e é reaproveitada.
        self._cliente = httpx.Client(base_url=url, timeout=60)

    def embed(self, texto: str) -> list[float]:
        r = self._cliente.post("/api/embeddings", json={"model": self._model, "prompt": texto})
        r.raise_for_status()
        return r.json()["embedding"]
