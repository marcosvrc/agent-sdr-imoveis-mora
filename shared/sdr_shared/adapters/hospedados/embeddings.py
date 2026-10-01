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
    NOME = "OpenAI"

    def __init__(self, api_key: str, model: str, dimensoes: int = 1024):
        if not api_key:
            raise RuntimeError(
                "SDR_EMBEDDINGS_PROVIDER=openai exige OPENAI_API_KEY (sem o prefixo SDR_ — é o nome "
                "que a biblioteca procura no ambiente).")
        self._key, self._model, self.dimensoes = api_key, model, dimensoes

    def _corpo(self, texto: str) -> dict:
        return {"model": self._model, "input": texto, "dimensions": self.dimensoes}

    def embed(self, texto: str) -> list[float]:
        r = httpx.post(self.URL, timeout=60,
                       headers={"Authorization": f"Bearer {self._key}"},
                       json=self._corpo(texto))
        if r.status_code >= 400:
            # A mensagem do provedor é específica (chave inválida, cota, modelo inexistente) e é
            # exatamente o que quem está indexando precisa ler. O corpo não traz segredo.
            raise RuntimeError(f"embeddings da {self.NOME} responderam {r.status_code}: {r.text[:300]}")
        vetor = r.json()["data"][0]["embedding"]
        if len(vetor) != self.dimensoes:
            # Guarda contra um padrão que mude do lado deles: melhor parar aqui do que gravar um
            # vetor de tamanho errado e descobrir na primeira busca do cliente. Pelo OpenRouter é
            # também o que denuncia um endpoint que não repassou o `dimensions`.
            raise RuntimeError(f"esperava {self.dimensoes} dimensões e vieram {len(vetor)}"
                               + (" — o provedor pode ter ignorado o parâmetro `dimensions`"
                                  if len(vetor) > self.dimensoes else ""))
        return vetor


class OpenRouterEmbedder(OpenAIEmbedder):
    """Embeddings pelo OpenRouter (ADR-0016): a mesma chave dos modelos de conversa, sem precisar da
    chave da OpenAI.

    **Mesmo modelo, mesmos vetores.** `openai/text-embedding-3-small` pelo OpenRouter é o modelo que
    o `OpenAIEmbedder` chama direto; pedindo as mesmas 1024 dimensões, o vetor é o mesmo e o índice
    já gravado continua valendo — trocar de caminho não obriga a reindexar. Trocar de MODELO obriga,
    como sempre (ver o docstring do módulo).

    **Privacidade — e por que aqui não vai `zdr`.** O texto que vira vetor inclui a pergunta do
    cliente, e `data_collection: deny` vai em toda chamada (nenhum endpoint que treine com o dado).
    A retenção zero, obrigatória na conversa, fica de fora de propósito: ela não aparece entre as
    preferências documentadas do endpoint de embeddings, e nenhum modelo de embedding estava na lista
    de endpoints ZDR do OpenRouter (2026-09-28). Exigi-la derrubaria toda busca — e a busca que falha
    não quebra nada visível: o RAG passa a dizer "vou confirmar com o corretor" para tudo. Sem ela, a
    postura é a mesma de chamar a OpenAI direto, que também não é retenção zero.
    """

    NOME = "OpenRouter"

    def __init__(self, api_key: str, model: str, dimensoes: int = 1024, url: str = "https://openrouter.ai/api/v1"):
        if not api_key:
            raise RuntimeError("SDR_EMBEDDINGS_PROVIDER=openrouter exige SDR_OPENROUTER_API_KEY.")
        # Sem fornecedor no ID, é o modelo da OpenAI — o mesmo que o caminho direto usa.
        super().__init__(api_key, model if "/" in model else f"openai/{model}", dimensoes)
        self.URL = f"{url.rstrip('/')}/embeddings"

    def _corpo(self, texto: str) -> dict:
        return {**super()._corpo(texto), "provider": {"data_collection": "deny"}}
