"""Resolve cada porta na implementação concreta.

Houve aqui uma escolha por `SDR_PROFILE` entre dois conjuntos de adaptadores, hospedados e
locais. Os hospedados foram removidos do projeto, então broker, scheduler e embeddings têm UMA
implementação cada e não há o que escolher.

As portas (os `Protocol` ao lado) ficam, e não por simetria: são o ponto onde o teste substitui a
infraestrutura, são o contrato escrito de cada dependência, e são onde uma segunda implementação
entraria sem tocar em quem chama. `get_calendario` e `get_crm` continuam com duas de verdade.

`SDR_PROFILE` continua existindo, com outro papel: é ele que decide se o token estático de
desenvolvimento vale (ver `seguranca/painel.py` e `api/auth.py`). O padrão passou a ser `local`.
"""
import inspect
import logging
import re
from functools import lru_cache
from ..config import get_settings
from .. import papeis as P

log = logging.getLogger("ports")


@lru_cache
def get_broker():
    from ..adapters.local.broker import RedisBroker
    return RedisBroker()


@lru_cache
def get_scheduler():
    from ..adapters.local.scheduler import PostgresScheduler
    return PostgresScheduler()


@lru_cache
def get_calendario():
    """Google quando há credencial de aplicativo configurada; senão, a agenda do próprio banco.
    A escolha é por aplicativo; se um corretor não conectou a agenda dele, o adaptador do Google
    devolve a ocupação interna do mesmo jeito."""
    s = get_settings()
    if s.google_client_id and s.google_client_secret:
        from ..adapters.google.calendario import CalendarioGoogle
        return CalendarioGoogle()
    from ..adapters.local.calendario import CalendarioLocal
    return CalendarioLocal()


@lru_cache
def get_crm():
    """O CRM entra quando está configurado, e o padrão é não ter.

    A escolha não é por `SDR_PROFILE`, como as outras portas, e sim por configuração presente: o
    perfil diz onde a Mora roda, não se a imobiliária tem CRM. Rodar local com CRM e rodar local
    sem CRM são os dois casos normais.
    """
    from ..adapters.crm.via_mcp import CRMviaMCP
    adaptador = CRMviaMCP()
    if adaptador.habilitado():
        return adaptador
    from ..adapters.crm.ausente import CRMAusente
    return CRMAusente()


@lru_cache
def get_embedder():
    """Ollama (local, sem chave), OpenAI ou OpenRouter (sem container). Todos devolvem 1024 dimensões.

    Provedor desconhecido levanta em vez de cair no padrão: gravar vetor de outro modelo no mesmo
    índice não dá erro nenhum na hora — dá resultado de busca errado depois, que é muito pior de
    diagnosticar.
    """
    s = get_settings()
    provider = (s.embeddings_provider or "ollama").strip().lower()
    if provider == "ollama":
        from ..adapters.local.embeddings import OllamaEmbedder
        return OllamaEmbedder(s.ollama_url, s.ollama_embedding_model)
    if provider == "openai":
        import os
        from ..adapters.hospedados.embeddings import OpenAIEmbedder
        # `OPENAI_API_KEY` cru, sem o prefixo SDR_: é o nome que a própria biblioteca da OpenAI
        # procura, e o caminho do LLM já usa esse mesmo. Duas variáveis para a mesma chave seria
        # uma a mais para alguém preencher pela metade.
        return OpenAIEmbedder(os.environ.get("OPENAI_API_KEY", ""), s.embeddings_model, s.embeddings_dimensoes)
    if provider == "openrouter":
        from ..adapters.hospedados.embeddings import OpenRouterEmbedder
        return OpenRouterEmbedder(s.openrouter_api_key or "", s.embeddings_model, s.embeddings_dimensoes,
                                  url=s.openrouter_url)
    raise RuntimeError(f"SDR_EMBEDDINGS_PROVIDER='{provider}' não é suportado. Use ollama, openai ou openrouter.")


# Prefixos que os IDs de modelo da Anthropic carregam em alguns provedores hospedados. Nenhum
# deles está no projeto hoje, mas o repertório fica: um `.env` antigo pode ter `anthropic.claude-…`
# gravado, e mandar isso para a API direta da Anthropic dá 404 num lugar que não explica a causa.
_PREFIXOS_HOSPEDADOS = ("anthropic.", "us.", "eu.", "apac.")

# Famílias de modelo por provedor. OpenAI é outra família: não existe `claude-sonnet-4-5` lá.
# O OpenRouter não é uma família de modelo, é um intermediário: seus IDs são `fornecedor/modelo`
# (`anthropic/claude-haiku-4.5`, `google/gemini-3.5-flash-lite`) e a barra é o que os identifica.
_FAMILIA = {
    "openai": ("gpt-", "o1", "o3", "o4"),
    "anthropic": ("claude",),
}

# Equivalente por PAPEL quando o modelo configurado não existe no provedor — o caso do fallback
# entre famílias. Sem esta tabela, cair da Anthropic para a OpenAI mandaria "claude-sonnet-4-5" para
# a OpenAI e voltaria 404: o reserva falharia exatamente no momento em que ele existe para servir.
# Pareado por posição na escala, não por nome: conversa ↔ modelo bom, roteamento ↔ modelo barato.
# Papéis que herdam (extracao, informacoes) não precisam de linha: caem na do pai (ver `_equivalente`).
_EQUIVALENTE = {
    "openai":    {"conversa": "gpt-5.6-terra", "analise": "gpt-5.6-terra", "roteamento": "gpt-5.6-luna"},
    "anthropic": {"conversa": "claude-sonnet-4-5", "analise": "claude-sonnet-4-5", "roteamento": "claude-haiku-4-5"},
    # Os mesmos modelos da Anthropic, pelo OpenRouter: quem cai de outro fornecedor para ele precisa
    # de um ID que exista lá, e o par de papéis continua o mesmo.
    "openrouter": {"conversa": "anthropic/claude-sonnet-4.5", "analise": "anthropic/claude-sonnet-4.5",
                   "roteamento": "anthropic/claude-haiku-4.5"},
}

_SUFIXO_DATA = re.compile(r"-\d{8}$")
_VERSAO_TRACO = re.compile(r"-(\d+)-(\d+)$")       # claude-haiku-4-5  → claude-haiku-4.5
_VERSAO_PONTO = re.compile(r"-(\d+)\.(\d+)$")      # claude-haiku-4.5  → claude-haiku-4-5


def familia_de(model: str) -> str | None:
    """anthropic | openai | openrouter | None (Ollama e desconhecidos)."""
    m = (model or "").strip().lower()
    if "/" in m:
        return "openrouter"
    m = normalizar_modelo(m, "anthropic")
    for provedor, prefixos in _FAMILIA.items():
        if m.startswith(prefixos):
            return provedor
    return None


def para_openrouter(model: str) -> str | None:
    """ID direto → ID do OpenRouter, quando o fornecedor é conhecido.

    A Anthropic escreve a versão com traço (`claude-haiku-4-5`) e o OpenRouter com ponto
    (`anthropic/claude-haiku-4.5`). Sufixo de data sai: o OpenRouter publica o alias, não o snapshot.
    """
    if "/" in (model or ""):
        return model
    familia = familia_de(model)
    if familia == "anthropic":
        nome = _SUFIXO_DATA.sub("", normalizar_modelo(model, "anthropic"))
        return "anthropic/" + _VERSAO_TRACO.sub(r"-\1.\2", nome)
    if familia == "openai":
        return "openai/" + model
    return None


def de_openrouter(model: str, provider: str) -> str | None:
    """ID do OpenRouter → ID direto no provedor pedido, quando é o mesmo fornecedor."""
    fornecedor, _, nome = (model or "").partition("/")
    if provider == "anthropic" and fornecedor == "anthropic":
        return _VERSAO_PONTO.sub(r"-\1-\2", nome)
    if provider == "openai" and fornecedor == "openai":
        return nome
    return None


def _equivalente(provider: str, papel: str) -> str | None:
    tabela = _EQUIVALENTE.get(provider, {})
    return next((tabela[p] for p in P.cadeia(papel) if p in tabela), None)


def catalogo_de_modelos(tabela: dict | None = None) -> dict[str, list[str]]:
    """Modelos que o painel pode oferecer, agrupados por provedor.

    Sai da MESMA tabela de preços que o `PUT /config/modelos` usa para recusar. Uma lista escrita à
    mão no frontend ofereceria opções que o backend depois rejeita — o combo estaria mentindo sobre
    o que dá para salvar. Assim, cadastrar um preço novo faz o modelo aparecer na tela sem tocar no
    React, e a tela nunca oferece modelo sem preço, que é justamente o que desliga o teto mensal.

    Ollama fica de fora de propósito: o que existe lá depende de qual modelo a máquina baixou, e uma
    lista fixa ofereceria o que o `ollama pull` ainda não trouxe. Para ele a tela cai no campo livre,
    que é o comportamento honesto para um provedor que só a máquina conhece.

    O OpenRouter só aparece quando há algum preço `fornecedor/modelo` cadastrado — é o
    `POST /config/modelos/openrouter/sincronizar` que os traz. Os 400 modelos do catálogo dele no
    combo não ajudariam ninguém a escolher.
    """
    from ..governanca.precos import PRECOS_PADRAO

    saida: dict[str, list[str]] = {p: [] for p in _FAMILIA}
    roteados: list[str] = []
    for modelo in {**PRECOS_PADRAO, **(tabela or {})}:
        if "/" in modelo:
            roteados.append(modelo)
            continue
        for provedor, prefixos in _FAMILIA.items():
            if modelo.lower().startswith(prefixos):
                saida[provedor].append(modelo)
                break
    if roteados:
        saida["openrouter"] = roteados
    return {p: sorted(m) for p, m in saida.items()}


def modelo_do_provedor(model: str, provider: str, papel: str = "conversa") -> str:
    """Devolve um ID que EXISTE no provedor pedido.

    Mesma família: só ajusta o prefixo. Mesmo fornecedor por outro caminho (Anthropic direta ↔
    Anthropic pelo OpenRouter): traduz o formato do ID. Família diferente: troca pelo equivalente do
    papel, porque traduzir o nome não faria o modelo existir lá.
    """
    familia = familia_de(model)
    if provider == "openrouter":
        return para_openrouter(model) or _equivalente(provider, papel) or model
    if familia == provider:
        return normalizar_modelo(model, provider)
    if familia == "openrouter" and (direto := de_openrouter(model, provider)):
        return direto
    return _equivalente(provider, papel) or normalizar_modelo(model, provider)


def normalizar_modelo(model: str, provider: str) -> str:
    """Tira os prefixos de provedor hospedado de um ID da Anthropic.

    `us.anthropic.claude-sonnet-4-5` e `claude-sonnet-4-5` são o MESMO modelo; só a API direta não
    aceita o primeiro. Continuar limpando isso protege quem tem um `.env` herdado."""
    if provider == "anthropic":
        mudou = True
        while mudou:                      # `us.anthropic.claude-…` tem dois prefixos empilhados
            mudou = False
            for p in _PREFIXOS_HOSPEDADOS:
                if model.startswith(p):
                    model, mudou = model[len(p):], True
        return model
    return model


def modo_do_agente() -> str:
    """normal | degradado | bloqueado, conforme o orçamento de LLM (painel de Governança)."""
    try:
        from ..db.governanca import estado_do_orcamento
        return estado_do_orcamento()["modo"]
    except Exception:                       # sem banco/tabela (testes, boot): não atrapalha
        return "normal"


# Uma tentativa a mais além da primeira, para todo provedor hospedado. O pior caso de um turno
# é `orcamento_do_turno_s()`; quem serializa turnos por lead (o lock do broker) usa esse número.
MAX_RETRIES = 1
# Chamadas de modelo em sequência num turno, no pior caso: rota (supervisor), extração do cartão,
# a resposta e a extração do consultor quando o turno passa do qualificador para ele.
CHAMADAS_POR_TURNO = 4


def orcamento_do_turno_s(timeout_s: float | None = None) -> float:
    """Quanto um turno pode levar no pior caso: cada chamada de modelo tenta (1 + MAX_RETRIES) vezes
    até o timeout em até dois provedores (principal e reserva), e o turno faz até
    CHAMADAS_POR_TURNO chamadas. Mais uma folga para banco e embeddings. É a régua do lock por lead
    — abaixo dela, o lock expira com o turno em curso e duas respostas saem para a mesma mensagem.
    Media UMA chamada só: com o modelo lento, o lock vencia no meio do turno."""
    espera = timeout_s or _timeout_do_painel() or get_settings().llm_timeout_s
    return espera * (1 + MAX_RETRIES) * 2 * CHAMADAS_POR_TURNO + 30


_EFEMERO = {"type": "ephemeral"}


def _bloco_marcado(msg):
    """CÓPIA da mensagem com `cache_control` no último bloco de texto.

    Cópia, e não edição no lugar, porque estas mensagens são o histórico que vive no checkpoint do
    grafo: marcá-las no original gravaria metadado de transporte dentro do estado da conversa.
    """
    conteudo = getattr(msg, "content", None)
    if isinstance(conteudo, str) and conteudo:
        blocos = [{"type": "text", "text": conteudo}]
    elif isinstance(conteudo, list) and conteudo and isinstance(conteudo[-1], dict):
        blocos = [dict(b) for b in conteudo]
    else:
        return msg                       # vazio, ou formato que não sabemos marcar: passa reto
    if blocos[-1].get("type") != "text":
        return msg
    blocos[-1] = {**blocos[-1], "cache_control": _EFEMERO}
    try:
        return msg.model_copy(update={"content": blocos})
    except AttributeError:               # não é mensagem do LangChain: não mexe
        return msg


def marcar_cache(entrada):
    """Dois pontos de corte: fim do system e fim do histórico.

    Um só no system quase nunca engata — medido: blindagem + persona + prompt do nó dão de 730 a
    1160 tokens, e o mínimo da Anthropic é 1024 no Sonnet e 2048 no Haiku. Quem passa do mínimo é o
    prefixo COM o histórico, e é por isso que o segundo corte existe: ele deixa o turno seguinte do
    mesmo lead reler tudo até ali por 10% do preço, desde que caia dentro do TTL de 5 min.

    Entrada que não é lista de mensagens (o caminho `texto()`, usado pelo supervisor e pela
    extração) volta intacta: ali não há prefixo reaproveitável.
    """
    if not isinstance(entrada, list) or not entrada:
        return entrada
    cortes = {len(entrada) - 1}
    for i, m in enumerate(entrada):
        if getattr(m, "type", None) == "system":
            cortes.add(i)
            break
    saida = list(entrada)
    for i in cortes:
        saida[i] = _bloco_marcado(saida[i])
    return saida


class ModeloComCacheDePrompt:
    """Marca o prefixo do prompt para o cache do provedor: Anthropic direta, e Anthropic e Qwen pelo
    OpenRouter (ver `MARCA_CACHE_OPENROUTER`).

    `cache_control` é campo da API da Anthropic: mandá-lo para a OpenAI direta é erro de requisição,
    e a OpenAI já faz cache de prefixo sozinha, sem marcação. Ollama não tem o conceito. O OpenRouter
    repassa a marcação aos fornecedores que a exigem e ignora nos que fazem cache sozinhos.

    Ligar é seguro mesmo quando não engata: abaixo do mínimo de tokens o provedor ignora a marca em
    silêncio, e o texto do prompt não muda — marcação é metadado, não conteúdo. Se engatou ou não
    aparece em `uso_llm.tokens_cache_leitura`, que a tela de Governança já soma.
    """

    def __init__(self, modelo):
        self._modelo = modelo

    def invoke(self, entrada, *a, **kw):
        return self._modelo.invoke(marcar_cache(entrada), *a, **kw)

    def with_structured_output(self, schema, **kw):
        return ModeloComCacheDePrompt(self._modelo.with_structured_output(schema, **kw))

    def __getattr__(self, nome):
        return getattr(self._modelo, nome)


# Teto de saída por papel: a tabela mora em `sdr_shared.papeis`; o nome fica aqui porque é onde
# quem lê o factory procura.
MAX_TOKENS = P.MAX_TOKENS

# Modelo que raciocina antes de responder gasta tokens de raciocínio DENTRO do `max_tokens`. Com o teto
# de uma fala de mensageiro, o raciocínio come o orçamento e a resposta sai vazia ou cortada — a
# Anthropic devolve `stop_reason: max_tokens`, o OpenRouter `finish_reason: length`. O multiplicador dá
# espaço ao raciocínio sem mudar o tamanho da resposta, que continua limitado pelo prompt.
FOLGA_RACIOCINIO = 4

_CLAUDE = re.compile(r"claude-(opus|sonnet|haiku|fable|mythos)-(\d+)(?:[-.](\d+))?")


def _nome_base(model: str) -> str:
    """`anthropic/claude-sonnet-5.5` → `claude-sonnet-5.5`; `us.anthropic.claude-…` → `claude-…`."""
    return normalizar_modelo((model or "").split("/")[-1].strip().lower(), "anthropic")


def raciocina_por_padrao(model: str) -> bool:
    """Modelos que pensam antes de responder quando ninguém pede o contrário.

    Claude: Sonnet 5+, Opus 5+, Fable e Mythos (o Haiku 4.5 não). OpenAI: GPT-5 (fora os `-chat`),
    GPT-6 e a série o. Gemini 3.x. A lista é por nome porque é a única informação que existe antes da
    primeira chamada — e errar para o lado de "raciocina" custa só teto de tokens maior.
    """
    nome = _nome_base(model)
    if m := _CLAUDE.search(nome):
        familia, maior = m.group(1), int(m.group(2))
        return familia in ("fable", "mythos") or (familia != "haiku" and maior >= 5)
    if nome.startswith(("gpt-5", "gpt-6")) and "chat" not in nome:
        return True
    return nome.startswith(("o1", "o3", "o4", "gemini-3"))


def recusa_temperatura(model: str) -> bool:
    """Modelos que devolvem 400 para `temperature` fora do padrão, em QUALQUER requisição.

    Anthropic: Sonnet 5+, Opus 4.7+, Fable, Mythos (docs de thinking, 2026-09). OpenAI: GPT-5/GPT-6
    com raciocínio — o `langchain-openai` já retira a temperatura do GPT-5 sozinho, mas não conhece o
    GPT-6. Mandar a temperatura para esses modelos não degrada: derruba toda chamada.
    """
    nome = _nome_base(model)
    if m := _CLAUDE.search(nome):
        familia, maior, menor = m.group(1), int(m.group(2)), int(m.group(3) or 0)
        if familia in ("fable", "mythos"):
            return True
        if familia == "opus":
            return (maior, menor) >= (4, 7)
        return familia == "sonnet" and maior >= 5
    return nome.startswith(("gpt-5", "gpt-6", "o1", "o3", "o4")) and "chat" not in nome


def _aceita(cls, campo: str) -> bool:
    """O campo existe nesta versão da biblioteca? `reasoning_effort` do ChatAnthropic, por exemplo,
    é recente: passá-lo a uma versão antiga quebraria o provedor inteiro por um ajuste de latência."""
    try:
        return campo in getattr(cls, "model_fields", {})
    except Exception:
        return False


class SaidaEstruturadaNativa:
    """Pede a saída estruturada NATIVA da Anthropic (`method="json_schema"`) em vez de tool calling.

    Com raciocínio ligado, a Anthropic não aceita ferramenta forçada: o `with_structured_output`
    padrão deixa de forçar a chamada, e quando o modelo responde em texto a extração levanta
    `OutputParserException` — que o qualificador engole, devolvendo o cartão sem mudança. O cliente
    informa o bairro e a Mora pergunta o bairro de novo. O Sonnet 5.5 não deixa desligar o raciocínio,
    então o caminho é o schema nativo, que funciona com ele ligado.
    """

    def __init__(self, modelo):
        self._modelo = modelo

    def invoke(self, *a, **kw):
        return self._modelo.invoke(*a, **kw)

    def with_structured_output(self, schema, **kw):
        kw.setdefault("method", "json_schema")
        return self._modelo.with_structured_output(schema, **kw)

    def __getattr__(self, nome):
        return getattr(self._modelo, nome)


def _sem_texto(resposta) -> bool:
    """Sem texto e sem chamada de ferramenta: nada que o nó possa usar."""
    if getattr(resposta, "tool_calls", None):
        return False
    c = getattr(resposta, "content", resposta)
    if isinstance(c, list):
        c = " ".join(b.get("text") or "" if isinstance(b, dict) else str(b) for b in c)
    return not str(c or "").strip()


class ModeloOpenRouter:
    """Dois clientes do mesmo modelo: um para conversa, outro para saída estruturada.

    A diferença é `provider.require_parameters`. Ligado, o OpenRouter só roteia para quem aceita
    TODOS os parâmetros da requisição — é o que garante que a extração caia num endpoint que
    respeita o schema, em vez de num que ignora `response_format` e devolve texto livre (que o
    qualificador engoliria sem erro). Mas ligado também na conversa, um parâmetro opcional que um
    endpoint não declara (a temperatura, o raciocínio) excluiria endpoints bons por nada.
    """

    def __init__(self, livre, estrito, por_ferramenta: bool = False, forcar_ferramenta: bool = True):
        self._livre, self._estrito = livre, estrito
        self._por_ferramenta, self._forcar = por_ferramenta, forcar_ferramenta

    def invoke(self, *a, **kw):
        r = self._livre.invoke(*a, **kw)
        if _sem_texto(r):
            # Modelo que raciocina às vezes gasta a vez inteira pensando e devolve conteúdo vazio. O
            # filtro de saída troca vazio pelo texto de reserva ("me conta o que você procura…"), e
            # um cliente que tinha acabado de dizer tudo recebeu essa pergunta de volta. Uma segunda
            # tentativa quase sempre traz o texto.
            log.warning("resposta vazia de %s; tentando de novo", getattr(self._livre, "model_name", "?"))
            r = self._livre.invoke(*a, **kw)
        return r

    def with_structured_output(self, schema, **kw):
        if self._por_ferramenta:
            r = estruturado_por_ferramenta(self._estrito, schema, forcar=self._forcar)
        else:
            r = self._estrito.with_structured_output(schema, **kw)
        # O OpenRouter às vezes devolve o erro do provedor de trás com status 200 e sem `choices`,
        # e o cliente da OpenAI estoura `'NoneType' object is not iterable`. Em testes reais foi
        # metade das extrações do GPT-6 Luna, cada uma caindo no reserva direto com 3 a 6 s a mais.
        # A falha é instantânea e costuma não se repetir: uma segunda tentativa no próprio
        # OpenRouter sai mais barata que o reserva.
        return r.with_retry(retry_if_exception_type=(TypeError,), stop_after_attempt=2,
                            wait_exponential_jitter=False)

    def __getattr__(self, nome):
        return getattr(self._livre, nome)


def estruturado_por_ferramenta(modelo, schema, forcar: bool = True):
    """Saída estruturada por CHAMADA DE FERRAMENTA, para endpoints que não aceitam schema.

    Pelo OpenRouter com retenção zero, o Claude Sonnet 5 só tem endpoint no Bedrock, que declara
    `tools` mas não `structured_outputs` — e o mesmo vale para vários hosts de DeepSeek e GLM. Com
    `require_parameters` ligado, pedir schema a eles deixa o OpenRouter sem endpoint para rotear:
    toda extração do cartão falharia. Ferramenta eles aceitam.

    `forcar=False` para Claude: com raciocínio ligado (padrão nos 5.x, e o Sonnet 5.5 nem deixa
    desligar), a Anthropic não aceita ferramenta forçada. Com uma ferramenta só e o prompt pedindo o
    cartão, o modelo a chama; se não chamar, o parser devolve None e o qualificador mantém o cartão
    anterior — o mesmo caminho de uma extração que falhou.
    """
    from langchain_core.output_parsers.openai_tools import JsonOutputKeyToolsParser, PydanticToolsParser
    from langchain_core.utils.function_calling import convert_to_openai_tool
    from pydantic import BaseModel

    ferramenta = convert_to_openai_tool(schema)
    nome = ferramenta["function"]["name"]
    # Sem forçar, `tool_choice` nem vai: "auto" já é o padrão, e mandá-lo explícito faria o
    # `require_parameters` exigir que o endpoint declare `tool_choice` também.
    ligado = modelo.bind_tools([ferramenta], tool_choice=nome if forcar else None)
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return ligado | PydanticToolsParser(tools=[schema], first_tool_only=True)
    return ligado | JsonOutputKeyToolsParser(key_name=nome, first_tool_only=True)


def preferencias_openrouter(papel: str, estrito: bool = False) -> dict:
    """O objeto `provider` de cada requisição ao OpenRouter.

    `data_collection: deny` e `zdr` não são opção de desempenho, são a condição para o texto do
    cliente passar por um intermediário (ADR-0016): com eles, o OpenRouter só usa endpoints que não
    guardam nem treinam com o dado.
    """
    s = get_settings()
    pref: dict = {"sort": P.ORDENACAO_OPENROUTER.get(papel, "throughput"), "data_collection": "deny"}
    if s.openrouter_zdr:
        pref["zdr"] = True
    if estrito:
        pref["require_parameters"] = True
    return pref


# Fornecedores que, pelo OpenRouter, só fazem cache com `cache_control` explícito no bloco. Os demais
# (OpenAI, Gemini, DeepSeek, Grok…) fazem cache de prefixo sozinhos — marcar seria ruído. Documentação
# de prompt caching do OpenRouter, 2026-09. O cache em memória não conta como retenção, então vale
# com o ZDR ligado; e o OpenRouter manda chamadas seguidas do mesmo modelo ao mesmo provedor
# ("sticky routing") justamente para o cache pegar.
MARCA_CACHE_OPENROUTER = ("anthropic/", "qwen/")


_ORDEM_ESFORCO = ("none", "minimal", "low", "medium", "high", "xhigh", "max")
# Sem catálogo, os que se sabe que não desligam o raciocínio (a primeira matriz real mediu:
# "Reasoning is mandatory for this endpoint and cannot be disabled", em toda chamada do gpt-oss).
_RACIOCINIO_OBRIGATORIO = ("openai/gpt-oss-",)


def esforco_openrouter(model: str, pedido: str) -> str:
    """O esforço do papel, ajustado ao que o modelo aceita.

    Só intervém num caso: o papel pede `none` (roteamento, extração) e o modelo não deixa desligar.
    Aí vai o menor esforço que ele aceita — pensar um pouco é melhor que falhar em toda chamada. Os
    demais pedidos passam como estão: o OpenRouter já traduz o esforço para o que cada provedor
    entende, e mexer neles mudaria o que a matriz mediu.
    """
    if pedido != "none":
        return pedido
    from ..adapters.hospedados.openrouter import config_raciocinio
    cfg = config_raciocinio(model)
    if cfg is None:
        return "low" if model.lower().startswith(_RACIOCINIO_OBRIGATORIO) else pedido
    aceitos = [e for e in _ORDEM_ESFORCO if e in (cfg.get("supported_efforts") or [])]
    if not cfg.get("mandatory"):
        return pedido                              # desliga: o OpenRouter aceita `none` mesmo fora da lista
    return next((e for e in aceitos if e != "none"), "low")


def _construir_openrouter(model: str, temp: float, papel: str, teto: int, cb, espera: float):
    from langchain_openai import ChatOpenAI
    from ..adapters.hospedados.openrouter import parametros_suportados

    s = get_settings()
    suportados = parametros_suportados(model)          # None = catálogo indisponível: decide pelo nome
    raciocina = raciocina_por_padrao(model) or bool(suportados and "reasoning" in suportados)
    usa_temp = not recusa_temperatura(model) and (suportados is None or "temperature" in suportados)
    teto = teto * FOLGA_RACIOCINIO if raciocina else teto

    def cliente(estrito: bool):
        corpo: dict = {"provider": preferencias_openrouter(papel, estrito)}
        # No cliente estrito, mandar `reasoning` a um modelo que não o declara o excluiria do roteamento.
        if raciocina and (not estrito or suportados is None or "reasoning" in suportados):
            corpo["reasoning"] = {"effort": esforco_openrouter(model, P.ESFORCO.get(papel, "low"))}
        return ChatOpenAI(model=model, temperature=temp if usa_temp else None, max_tokens=teto,
                          callbacks=cb, base_url=s.openrouter_url, api_key=s.openrouter_api_key,
                          timeout=espera, max_retries=MAX_RETRIES, extra_body=corpo,
                          default_headers={"X-Title": "Mora SDR"})

    # Schema quando o endpoint declara `structured_outputs`; ferramenta quando só declara `tools`.
    # Sem catálogo, Claude vai por ferramenta: com retenção zero ele só tem o Bedrock, sem schema.
    if suportados is not None:
        por_ferramenta = "structured_outputs" not in suportados and "tools" in suportados
    else:
        por_ferramenta = model.lower().startswith("anthropic/")
    modelo = ModeloOpenRouter(cliente(False), cliente(True), por_ferramenta=por_ferramenta,
                              forcar_ferramenta=not model.lower().startswith("anthropic/"))
    if s.prompt_cache and model.lower().startswith(MARCA_CACHE_OPENROUTER):
        # Mesmos dois cortes da Anthropic direta (fim do system, fim do histórico). Sem eles, trocar
        # a Anthropic direta pelo OpenRouter faria todo turno pagar o prefixo inteiro de novo.
        return ModeloComCacheDePrompt(modelo)
    return modelo


def _construir(provider: str, model: str, temp: float, papel: str, max_tokens: int = 600,
               registro: str | None = None):
    """Monta UM provedor. Separado de `get_chat_model` para o fallback montar o segundo pelo mesmo
    caminho — inclusive a tradução do ID do modelo, que é o pedaço chato de trocar de provedor e já
    estava resolvido aqui (ver `normalizar_modelo` e ADR-0009).

    `papel` escolhe o modelo equivalente quando a família muda; `registro` é o papel que a governança
    grava. Só diferem com o agente degradado: a conversa passa a ser ATENDIDA pelo modelo barato, mas
    continua sendo conversa — gravá-la como roteamento misturaria os dois na tela de comparação.
    """
    s = get_settings()
    from ..governanca import callbacks_para
    cb = callbacks_para(registro or papel, provider)
    funcao = registro or papel
    # A régua do timeout é a espera do CLIENTE, não o provedor — e quem descobre que ela está curta
    # demais é quem está olhando a conversa travar, com o sistema no ar. Por isso vem do painel.
    espera = _timeout_do_painel() or s.llm_timeout_s
    if provider != "ollama":
        model = modelo_do_provedor(model, provider, papel)
    raciocina = raciocina_por_padrao(model)
    teto = max_tokens * FOLGA_RACIOCINIO if raciocina else max_tokens
    temperatura = None if recusa_temperatura(model) else temp
    if provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        # Chave de organização precisa dizer em qual workspace cobrar; chave já escopada dispensa.
        headers = {"anthropic-workspace-id": s.anthropic_workspace_id} if s.anthropic_workspace_id else None
        extra = {}
        if raciocina and _aceita(ChatAnthropic, "reasoning_effort"):
            # O esforço mínimo da Anthropic é `low`; `none` do papel vira o menor que ela aceita.
            esforco = P.ESFORCO.get(funcao, "low")
            extra["reasoning_effort"] = "low" if esforco in ("none", "minimal") else esforco
        # timeout/retries curtos: melhor falhar rápido e acionar o fallback do que pendurar o cliente.
        # `MAX_RETRIES=1`: com 2, o pior caso era 45 s × 3 tentativas × 2 provedores = 270 s de
        # cliente olhando para "digitando" — e o lock por lead (180 s) expirava no meio.
        modelo = ChatAnthropic(model=model, temperature=temperatura, max_tokens=teto, default_headers=headers,
                               callbacks=cb, timeout=espera, max_retries=MAX_RETRIES, **extra)
        if s.prompt_cache:
            modelo = ModeloComCacheDePrompt(modelo)
        if raciocina and "method" in inspect.signature(ChatAnthropic.with_structured_output).parameters:
            modelo = SaidaEstruturadaNativa(modelo)
        return modelo
    if provider == "ollama":
        from langchain_ollama import ChatOllama
        return ChatOllama(model=model, base_url=s.ollama_url, temperature=temp, callbacks=cb, client_kwargs={"timeout": espera})
    if provider == "openai":
        from langchain_openai import ChatOpenAI
        # Reserva de produção (ADR-0009): ao contrário do OpenRouter, é o próprio fornecedor do
        # modelo, sem intermediário no caminho do dado do cliente. Mesmos timeout e retries curtos
        # da Anthropic — a régua é a espera do cliente, não o provedor.
        # A chave sai de OPENAI_API_KEY no ambiente, como a da Anthropic sai de ANTHROPIC_API_KEY:
        # é o nome que a própria biblioteca procura. Passar `api_key=` explícito anularia esse
        # caminho para quem exporta a variável convencional.
        extra = {}
        if raciocina and _aceita(ChatOpenAI, "reasoning_effort"):
            # `low` e não `none`: o GPT-5 original não aceita `none`, e `low` vale na série inteira.
            # Sem isto o reserva raciocina no padrão (`medium`) — lento justo quando já é o plano B.
            extra["reasoning_effort"] = "low"
        return ChatOpenAI(model=model, temperature=temperatura, max_tokens=teto, callbacks=cb,
                          timeout=espera, max_retries=MAX_RETRIES, **extra)
    if provider == "openrouter":
        # Um intermediário no caminho do texto do cliente (ADR-0016): as preferências de provedor
        # (sem retenção, sem coleta) vão em TODA requisição, não como opção de quem configura.
        return _construir_openrouter(model, temp, funcao, max_tokens, cb, espera)
    raise RuntimeError(
        f"SDR_LLM_PROVIDER='{provider}' não é suportado. Use anthropic, openai, ollama ou openrouter.\n"
        "Levantar aqui é melhor que escolher um provedor por conta própria e o cliente descobrir "
        "pelo texto da resposta.")


class ModeloComFallback:
    """Tenta o provedor primário; se ele falhar, repete no reserva.

    Só entra em ação quando o primário já esgotou os retries internos dele — ou seja, quando o
    provedor está de fato indisponível, não numa oscilação. Nesse ponto tentar o outro provedor é
    melhor que devolver a mensagem de desculpa ao cliente, que é o que acontecia antes.

    Não usamos `Runnable.with_fallbacks` porque ele devolve um Runnable sem `with_structured_output`,
    e a extração do cartão depende justamente disso (`qualificador._extrair`).
    """

    def __init__(self, primario, reserva, nome_reserva: str):
        self._primario, self._reserva, self._nome = primario, reserva, nome_reserva

    def invoke(self, *a, **kw):
        try:
            return self._primario.invoke(*a, **kw)
        except Exception as e:
            log.warning("provedor primário falhou (%s); assumindo o reserva (%s)", type(e).__name__, self._nome)
            return self._reserva.invoke(*a, **kw)

    def with_structured_output(self, schema, **kw):
        return ModeloComFallback(self._primario.with_structured_output(schema, **kw),
                                 self._reserva.with_structured_output(schema, **kw), self._nome)

    def __getattr__(self, nome):            # o que não for invoke/structured segue para o primário
        return getattr(self._primario, nome)


def _escolha_do_painel(papel: str) -> tuple[str | None, str | None]:
    """O que o painel diz para ESTE papel, sem herdar do pai — a herança é resolvida em
    `modelo_efetivo`, que intercala painel e ambiente em cada nível."""
    try:
        from ..db import escolha_de_modelo
        return escolha_de_modelo(papel, herdar=False)
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return None, None


def _do_ambiente(papel: str) -> str | None:
    s = get_settings()
    v = {"conversa": s.model_conversa, "roteamento": s.model_roteamento, "extracao": s.model_extracao,
         "informacoes": s.model_informacoes, "analise": s.model_analise}.get(papel)
    return (v or "").strip() or None


def modelo_efetivo(papel: str) -> dict:
    """(modelo, provedor, origem) que o papel usa AGORA — a mesma resposta para o agente, a tela e o
    relatório de avaliação, que antes resolviam isso cada um à sua maneira.

    Precedência por nível, subindo a cadeia de herança: painel do papel → ambiente do papel → painel
    do pai → ambiente do pai. Assim quem fixa `SDR_MODEL_ANALISE` no ambiente não é atropelado por
    uma troca de conversa no painel, e quem não mexe em nada continua exatamente como antes.
    """
    s = get_settings()
    for nivel in P.cadeia(papel):
        do_painel, provedor = _escolha_do_painel(nivel)
        if do_painel:
            return {"modelo": do_painel, "provider": provedor or s.llm_provider, "origem": "painel", "de": nivel}
        if do_env := _do_ambiente(nivel):
            return {"modelo": do_env, "provider": provedor or s.llm_provider, "origem": "ambiente", "de": nivel}
    return {"modelo": s.model_conversa, "provider": s.llm_provider, "origem": "ambiente", "de": "conversa"}


def _timeout_do_painel() -> float | None:
    try:
        from ..db import operacao_numero
        v = operacao_numero("llm_timeout_s")
        return v if v and v > 0 else None        # 0 aqui seria "sem espera", que não faz sentido
    except Exception:                            # sem banco (testes, boot): o ambiente decide
        return None


def _reserva_do_painel() -> str | None:
    """Mesmo contrato do modelo por nível: o painel manda, o .env é o piso."""
    try:
        from ..db import reserva_do_painel
        return reserva_do_painel()
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return None


def get_chat_model(papel: str = "conversa"):
    """papel: um de `sdr_shared.papeis.PAPEIS`. Provedor: anthropic | openai | ollama | openrouter.
    Modelo e provedor saem do painel quando configurados lá, senão do .env (ADR-0010); papel vazio
    herda do pai (ADR-0016). Toda chamada é registrada para governança; se o orçamento estourou, todo
    papel é atendido pelo modelo barato. Com fallback definido, a queda de um provedor não vira turno
    perdido."""
    s = get_settings()
    # Degradar troca o MODELO, não o comportamento do papel. Antes a conversa degradada era montada
    # inteira como roteamento — temperatura 0.0 e o teto de tokens dele —, e a Mora ficava robótica
    # justamente quando já estava no modelo menor. `pedido` guarda o papel de origem para isso.
    pedido = papel if P.valido(papel) else "conversa"
    atende = P.BARATO if pedido != P.BARATO and modo_do_agente() == "degradado" else pedido
    efetivo = modelo_efetivo(atende)
    model, provider = efetivo["modelo"], efetivo["provider"]
    temp, teto = P.TEMPERATURA[pedido], P.MAX_TOKENS[pedido]
    primario = _construir(provider, model, temp, atende, max_tokens=teto, registro=pedido)
    escolhido = _reserva_do_painel()
    reserva = "" if escolhido == "nenhum" else (escolhido or (s.llm_provider_fallback or "").strip())
    if not reserva or reserva == provider:
        return primario
    return ModeloComFallback(primario, _construir(reserva, model, temp, atende, max_tokens=teto,
                                                  registro=pedido), reserva)
