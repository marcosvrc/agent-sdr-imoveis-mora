"""Embeddings por API, para quem não quer um Ollama rodando junto.

A razão de existir: com `SDR_LLM_PROVIDER=anthropic` — que é o caminho padrão — o Ollama passa a
existir SÓ para embeddings. Um container, um modelo de 1 GB e RAM na indexação, para uma chamada
que custa frações de centavo por API. Trocar tira um serviço inteiro do compose.

**As dimensões são o que manda aqui.** O schema declara `vector(1024)` em `imoveis.embedding` e
`documentos.embedding`, e vetor de tamanho errado não é degradação: é `ERROR: expected 1024
dimensions`. O `text-embedding-3` da OpenAI nasce com 1536 e aceita o parâmetro `dimensions` —
pedindo 1024, o schema não muda uma linha. É por isso que este adaptador sempre manda `dimensions`
em vez de confiar no padrão do modelo.

**Trocar de modelo invalida o índice.** Vetores de modelos diferentes não se comparam: a distância
de cosseno entre um `bge-m3` e um `text-embedding-3-small` é ruído com aparência de número. Depois
de trocar, `make seed` e `make docs-kb` de novo, inteiros. Não há migração parcial.
"""
import httpx


class OpenAIEmbedder:
    """`text-embedding-3-*` da OpenAI, truncado nas dimensões do schema.

    Sem o SDK: é um POST com um JSON, e o adaptador do Ollama ao lado já fazia assim. Uma dependência
    a menos na imagem é o ponto deste arquivo.
    """

    URL = "https://api.openai.com/v1/embeddings"

    def __init__(self, api_key: str, model: str, dimensoes: int = 1024):
        if not api_key:
            raise RuntimeError(
                "SDR_EMBEDDINGS_PROVIDER=openai exige OPENAI_API_KEY (sem o prefixo SDR_ — é o nome "
                "que a biblioteca procura no ambiente).")
        self._key, self._model, self.dimensoes = api_key, model, dimensoes

    def embed(self, texto: str) -> list[float]:
        r = httpx.post(self.URL, timeout=60,
                       headers={"Authorization": f"Bearer {self._key}"},
                       json={"model": self._model, "input": texto, "dimensions": self.dimensoes})
        if r.status_code >= 400:
            # A mensagem da OpenAI é específica (chave inválida, cota, modelo inexistente) e é
            # exatamente o que quem está indexando precisa ler. O corpo não traz segredo.
            raise RuntimeError(f"embeddings da OpenAI responderam {r.status_code}: {r.text[:300]}")
        vetor = r.json()["data"][0]["embedding"]
        if len(vetor) != self.dimensoes:
            # Guarda contra um padrão que mude do lado deles: melhor parar aqui do que gravar um
            # vetor de tamanho errado e descobrir na primeira busca do cliente.
            raise RuntimeError(f"esperava {self.dimensoes} dimensões e vieram {len(vetor)}")
        return vetor
