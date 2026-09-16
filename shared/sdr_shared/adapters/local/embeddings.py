"""Embeddings locais via Ollama (ex.: nomic-embed-text = 768 dims, bge-m3 = 1024 dims, multilíngue)."""
import httpx


class OllamaEmbedder:
    def __init__(self, url: str, model: str):
        self._url, self._model = url, model
        self.dimensoes = 1024 if "bge-m3" in model else 768

    def embed(self, texto: str) -> list[float]:
        r = httpx.post(f"{self._url}/api/embeddings", json={"model": self._model, "prompt": texto}, timeout=60)
        r.raise_for_status()
        return r.json()["embedding"]
