"""Configurações do agente editáveis pelo painel. Defaults aqui; overrides na tabela `configuracoes`.

`followup` é lido pelo agente em tempo de execução (sdr_shared/followup.py) — salvar aqui muda o
comportamento no próximo turno. As demais chaves ainda são declarativas.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sdr_shared import followup as politica_followup
from sdr_shared.config import get_settings
from sdr_shared.db import ConfigRepository
from sdr_shared.papeis import DESCRICAO, HERDA, PAPEIS
from ..auth import corretor_atual

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(corretor_atual)])

DEFAULTS: dict[str, dict] = {
    "agente": {"nome": "Mora", "empresa": "Vértice Imóveis", "tom": "cordial e direto", "max_frases": 3,
               "apresentar_como_assistente": True, "emojis": "raros"},
    # A fonte da verdade do follow-up é sdr_shared.followup.PADRAO — aqui só espelhamos,
    # para não existirem dois padrões divergindo com o tempo.
    "followup": dict(politica_followup.PADRAO),
    "agenda": {"slots": [10, 14, 16], "duracao_min": 60, "dias_uteis": True, "antecedencia_dias": 5},
    "cobertura": {"regioes": ["zona_sul", "zona_oeste", "zona_norte", "zona_leste", "centro"], "cidade": "São Paulo"},
    "handoff": {"palavras_gatilho": ["corretor", "atendente", "humano", "pessoa de verdade"], "auto_quando_quente": False},
    # Modelo por papel (ADR-0010, ADR-0016). Vazio = herda do papel pai ou usa o do .env, então dá
    # para mexer em um papel só e desfazer tudo com DELETE /config/modelos, sem precisar do banco.
    # `fallback_provider` vazio = usa o SDR_LLM_PROVIDER_FALLBACK do ambiente; a string "nenhum"
    # é o jeito de DESLIGAR o reserva pela tela sem mexer no .env. Sem ela, apagar o campo no
    # painel não conseguiria desfazer um fallback herdado do ambiente.
    "modelos": {**{campo: "" for p in PAPEIS for campo in (p, f"{p}_provider")}, "fallback_provider": ""},
    # Ajustes de operação. Vazio = usa o do ambiente; um valor explícito (inclusive `0` e `off`)
    # é decisão de quem está olhando o sistema no ar. A distinção entre "vazio" e "desligado" é o
    # que permite a tela desfazer algo herdado do `.env` — ver db/operacao.py.
    "operacao": {"llm_timeout_s": "", "transcricao": "", "acervo_refresh_s": ""},
}

PROVIDERS = ("", "anthropic", "openai", "ollama", "openrouter")


def _modelos_efetivos() -> dict:
    """O que o agente realmente vai usar no próximo turno — a tela mostra isto, não a intenção.
    A resolução é a do próprio agente (`modelo_efetivo`): se a tela resolvesse por conta própria,
    bastaria uma regra de herança diferente para ela mostrar um modelo e o agente usar outro."""
    from sdr_shared.ports.factory import modelo_efetivo
    return {p: modelo_efetivo(p) for p in PAPEIS}


def _catalogo() -> dict:
    """Modelos oferecidos no combo da tela, por provedor — a mesma lista que o PUT valida.

    Cair na tabela padrão (sem os preços cadastrados no painel) é aceitável porque o combo é
    sugestão: salvar continua passando por _validar_modelos, que recusa com o motivo. Mas vai para o
    log — uma lista que encolheu sozinha é exatamente o tipo de coisa que ninguém percebe.
    """
    from sdr_shared.ports.factory import catalogo_de_modelos
    try:
        from sdr_shared.db import UsoRepository
        return catalogo_de_modelos(UsoRepository().precos())
    except Exception:
        log.warning("preços do painel indisponíveis; combo de modelos cai na tabela padrão",
                    exc_info=True)
        return catalogo_de_modelos()


def _status_canais() -> dict:
    s = get_settings()
    return {"telegram": {"configurado": bool(getattr(s, "telegram_bot_token", "")), "usuario": getattr(s, "telegram_bot_username", "") or None},
            "web": {"configurado": True},
            "llm": {"provider": getattr(s, "llm_provider", "anthropic"), "modelo_conversa": getattr(s, "model_conversa", ""),
                    "modelo_roteamento": getattr(s, "model_roteamento", ""),
                    "fallback": getattr(s, "llm_provider_fallback", "") or None,
                    # o que está valendo de fato: painel quando preenchido, .env quando não
                    "efetivo": _modelos_efetivos(),
                    # o que a tela pode oferecer sem que o PUT recuse depois
                    "catalogo": _catalogo(),
                    # papéis na ordem da tela, com a descrição e de quem cada um herda quando vazio
                    "papeis": [{"papel": p, "descricao": DESCRICAO[p], "herda": HERDA.get(p)} for p in PAPEIS],
                    "openrouter": {"configurado": bool(get_settings().openrouter_api_key),
                                   "zdr": get_settings().openrouter_zdr}},
            "embeddings": {"provider": getattr(s, "embeddings_provider", "ollama"),
                           "modelo": (getattr(s, "embeddings_model", "") if getattr(s, "embeddings_provider", "") == "openai"
                                      else getattr(s, "ollama_embedding_model", "")),
                           "dimensoes": getattr(s, "embeddings_dimensoes", 1024)}}


@router.get("")
def obter():
    salvas = ConfigRepository().todas()
    if "followup" in salvas:
        salvas["followup"] = politica_followup.migrar(salvas["followup"])
    # só campos que o formato atual conhece: uma chave antiga esquecida no banco voltaria no PUT
    config = {k: {**v, **{ck: cv for ck, cv in salvas.get(k, {}).items() if ck in v}} for k, v in DEFAULTS.items()}
    return {"config": config, "defaults": DEFAULTS, "canais": _status_canais()}


@router.put("/{chave}")
def salvar(chave: str, body: dict):
    if chave not in DEFAULTS:
        raise HTTPException(404, f"chave desconhecida: {chave}")
    if chave == "followup":
        body = politica_followup.migrar(body)      # aceita o formato antigo em vez de recusar
    desconhecidas = set(body) - set(DEFAULTS[chave])
    if desconhecidas:
        raise HTTPException(422, f"campos desconhecidos em {chave}: {sorted(desconhecidas)}")
    _validar_tipos(chave, body)
    if chave == "followup":
        _validar_followup(body)
    if chave == "modelos":
        _validar_modelos(body)
    if chave == "operacao":
        _validar_operacao(body)
    ConfigRepository().salvar(chave, body)
    if chave == "followup":
        politica_followup.invalidar_cache()       # o agente lê isto a cada turno; vale já
    if chave == "modelos":
        from sdr_shared.db import invalidar_cache_modelos
        invalidar_cache_modelos()                 # sem isto o worker seguiria com o modelo antigo
    if chave == "operacao":
        from sdr_shared.db import invalidar_cache_operacao
        invalidar_cache_operacao()
    return {"chave": chave, "valor": {**DEFAULTS[chave], **body}}


@router.get("/modelos/comparacao")
def comparacao_de_modelos(dias: int = Query(30, ge=1, le=365)):
    """Custo, latência medida e papel recomendado por modelo — uma lista por papel, da mais barata
    para a mais cara.

    Uma lista POR PAPEL porque a ordem muda: o roteamento gasta quase tudo em entrada e a conversa
    em saída, então o modelo mais barato para um não é o mais barato para o outro.
    """
    from sdr_shared.db import UsoRepository
    from sdr_shared.governanca import comparar, recomendacoes
    from sdr_shared.ports.factory import _EQUIVALENTE, catalogo_de_modelos

    repo = UsoRepository()
    tabela, mixes, latencias = repo.precos(), repo.mix_por_papel(dias), repo.latencia_por_modelo(dias)
    catalogo, recomendado = catalogo_de_modelos(tabela), recomendacoes(_EQUIVALENTE)
    papeis = {p: comparar(catalogo=catalogo, mix=mixes.get(p, {}),
                          latencias=latencias.get(p, latencias.get("_geral", {})),
                          recomendado=recomendado, tabela=tabela, dias=dias)
              for p in PAPEIS}
    return {"dias": dias, "papeis": papeis}


# Seções cujo default "" significa "vazio = herda do ambiente" e que aceitam número no lugar: o
# tipo delas é conferido campo a campo em `_validar_operacao`, não pelo default.
_TIPO_PROPRIO = {"operacao"}


def _nome_do_tipo(v: object) -> str:
    return {bool: "verdadeiro/falso", int: "número", float: "número", str: "texto",
            list: "lista", dict: "objeto"}.get(type(v), type(v).__name__)


def _mesmo_tipo(valor: object, modelo: object) -> bool:
    # bool é subclasse de int em Python: sem separar, `true` passaria por número e `1` por booleano.
    if isinstance(modelo, bool) or isinstance(valor, bool):
        return isinstance(valor, bool) and isinstance(modelo, bool)
    if isinstance(modelo, (int, float)):
        return isinstance(valor, (int, float))
    return isinstance(valor, type(modelo))


def _validar_tipos(chave: str, body: dict) -> None:
    """Cada campo tem o tipo do seu default. Sem isto, `{"conversa": 123}` em /config/modelos
    chegava a `.strip()` e virava 500, e um `"max_frases": "três"` era gravado e quebrava quem lê.

    O formato aceito é o mesmo de antes — o default é a referência, e é o que o painel já manda.
    `null` continua aceito (o `GET` devolve o default no lugar); listas conferem o tipo dos itens
    pelo primeiro item do default."""
    if chave in _TIPO_PROPRIO:
        return
    for campo, valor in body.items():
        modelo = DEFAULTS[chave][campo]
        if valor is None:
            continue
        if not _mesmo_tipo(valor, modelo):
            raise HTTPException(422, f"{campo}: esperado {_nome_do_tipo(modelo)}, veio {_nome_do_tipo(valor)}")
        if isinstance(modelo, list) and modelo:
            if (ruim := next((x for x in valor if not _mesmo_tipo(x, modelo[0])), None)) is not None:
                raise HTTPException(422, f"{campo}: cada item precisa ser {_nome_do_tipo(modelo[0])} "
                                         f"(veio {ruim!r})")


def _validar_modelos(body: dict) -> None:
    """A trava que importa: modelo sem preço cadastrado zera o custo calculado, e com o custo em zero
    o teto mensal em dólar nunca é atingido — o guardrail de orçamento fica ligado só na aparência.
    Por isso salvar um modelo desconhecido é recusado, com o caminho para resolver."""
    from sdr_shared.db import UsoRepository
    from sdr_shared.governanca import preco_do_modelo

    if (reserva := (body.get("fallback_provider") or "").strip()):
        if reserva not in (*PROVIDERS, "nenhum"):
            raise HTTPException(422, f"fallback_provider: provedor desconhecido '{reserva}'")
        # Reserva igual ao primário não é erro de digitação inofensivo: são duas chamadas ao mesmo
        # provedor caído, e o cliente espera o dobro para receber a mesma falha.
        if reserva == (body.get("conversa_provider") or "").strip():
            raise HTTPException(422, "fallback_provider: o reserva não pode ser o mesmo provedor da "
                                     "conversa — seriam duas tentativas no provedor que caiu.")

    for nivel in PAPEIS:
        if (prov := body.get(f"{nivel}_provider")) and prov not in PROVIDERS:
            raise HTTPException(422, f"{nivel}_provider: provedor desconhecido '{prov}'")
        modelo = (body.get(nivel) or "").strip()
        if not modelo:
            continue
        if len(modelo) > 120 or any(c.isspace() for c in modelo):
            raise HTTPException(422, f"{nivel}: '{modelo}' não parece um identificador de modelo")
        provedor = (body.get(f"{nivel}_provider") or "").strip() or get_settings().llm_provider
        # Ollama roda local e não tem custo; os demais precisam de preço para a governança funcionar
        if provedor == "ollama":
            continue
        if preco_do_modelo(modelo, UsoRepository().precos()):
            continue
        # Pelo OpenRouter o preço existe publicado: buscar é melhor que mandar alguém digitar à mão.
        if provedor == "openrouter" and _sincronizar_precos([modelo])[0]:
            continue
        raise HTTPException(422, f"{nivel}: sem preço cadastrado para '{modelo}'. Cadastre em "
                                 f"Configurações → preços antes de usá-lo, senão o custo é "
                                 f"contabilizado como zero e o teto de orçamento para de valer.")


def _sincronizar_precos(modelos: list[str]) -> tuple[dict, list[str]]:
    """Grava na configuração `precos` o preço que o OpenRouter publica para cada modelo pedido.

    Só os pedidos, nunca o catálogo inteiro: são centenas de modelos, e cada preço cadastrado vira
    uma opção no combo da tela. Devolve (gravados, não encontrados). Falha de rede não grava nada.
    """
    from sdr_shared.adapters.hospedados.openrouter import precos_de
    from sdr_shared.db import UsoRepository

    try:
        achados, faltando = precos_de(modelos)
    except Exception as e:
        log.warning("não consegui sincronizar preços do OpenRouter: %s", e)
        return {}, list(modelos)
    if achados:
        repo = UsoRepository()
        repo.salvar_precos({**repo.precos(), **achados})
    return achados, faltando


@router.post("/modelos/openrouter/sincronizar")
def sincronizar_precos_openrouter(body: dict):
    """Traz do catálogo do OpenRouter o preço dos modelos informados (`{"modelos": ["google/…"]}`).

    É o que faz um modelo do OpenRouter aparecer no combo da tela e passar na trava de preço — sem
    alguém copiar quatro números de uma página para um formulário, que é onde preço errado nasce.
    """
    modelos = [str(m).strip() for m in (body.get("modelos") or []) if str(m).strip()]
    if not modelos:
        raise HTTPException(422, "informe `modelos`: a lista de IDs do OpenRouter (fornecedor/modelo)")
    if len(modelos) > 50:
        raise HTTPException(422, "no máximo 50 modelos por vez")
    if any("/" not in m for m in modelos):
        raise HTTPException(422, "IDs do OpenRouter têm o formato fornecedor/modelo, "
                                 "ex.: google/gemini-3.5-flash-lite")
    achados, faltando = _sincronizar_precos(modelos)
    if not achados and faltando:
        raise HTTPException(502, f"o OpenRouter não devolveu preço para: {', '.join(faltando)}")
    return {"gravados": achados, "nao_encontrados": faltando}


def _validar_operacao(body: dict) -> None:
    """Cada um destes números tem uma faixa em que ele ainda é o que promete ser."""
    for campo in ("llm_timeout_s", "acervo_refresh_s"):
        # `True` é int para o Python: passaria como 1 (e `False` como 0 = desligar o refresh).
        if isinstance(body.get(campo), bool):
            raise HTTPException(422, f"{campo}: informe um número de segundos, ou vazio para usar o do ambiente")
    t = body.get("llm_timeout_s")
    if t not in (None, ""):
        if not isinstance(t, (int, float)) or not 5 <= t <= 180:
            raise HTTPException(422, "llm_timeout_s: entre 5 e 180 segundos. Abaixo de 5 o modelo "
                                     "não termina de responder; acima de 180 o cliente já desistiu.")
    tr = body.get("transcricao") or ""
    if not isinstance(tr, str):
        raise HTTPException(422, "transcricao: informe auto, whisper_local, off — ou vazio para usar o do ambiente")
    tr = tr.strip()
    if tr and tr not in ("auto", "whisper_local", "off"):
        raise HTTPException(422, f"transcricao: valor desconhecido '{tr}' — use auto, whisper_local ou off")
    r = body.get("acervo_refresh_s")
    if r not in (None, ""):
        if not isinstance(r, (int, float)) or r < 0:
            raise HTTPException(422, "acervo_refresh_s: informe 0 para desligar, ou um número de segundos")
        if 0 < r < 60:
            raise HTTPException(422, "acervo_refresh_s: abaixo de 60s a reindexação pega o worker "
                                     "ainda ocupado com o follow-up. Use 0 para desligar.")


def _validar_followup(body: dict) -> None:
    """Erro de digitação aqui vira cliente cutucado de madrugada ou nunca — melhor recusar."""
    tempos = body.get("tempos_min")
    if tempos is not None:
        if not isinstance(tempos, list) or not tempos:
            raise HTTPException(422, "tempos_min: informe ao menos uma tentativa")
        if len(tempos) > 10:
            raise HTTPException(422, "tempos_min: no máximo 10 tentativas")
        if any(not isinstance(t, (int, float)) or t < 5 for t in tempos):
            raise HTTPException(422, "tempos_min: cada tentativa precisa ser um número ≥ 5 minutos")
    ritmo = body.get("ritmo")
    if ritmo is not None:
        if not isinstance(ritmo, dict):
            raise HTTPException(422, "ritmo: informe um multiplicador por temperatura")
        for temperatura, fator in ritmo.items():
            if temperatura not in politica_followup.PADRAO["ritmo"]:
                raise HTTPException(422, f"ritmo: temperatura desconhecida '{temperatura}'")
            if not isinstance(fator, (int, float)) or not 0.05 <= float(fator) <= 10:
                raise HTTPException(422, f"ritmo: o fator de '{temperatura}' deve ficar entre 0,05 e 10")
    for campo in ("janela_inicio", "janela_fim"):
        if campo in body and not _hora_valida(body[campo]):
            raise HTTPException(422, f"{campo}: use o formato HH:MM")
    ini, fim = body.get("janela_inicio"), body.get("janela_fim")
    # Compara as HORAS, não o texto: como texto, "9:00" >= "18:00" (o "9" vem depois do "1") e
    # uma janela das 9h às 18h era recusada.
    if ini and fim and _hora_valida(ini) and _hora_valida(fim) and _minutos(ini) >= _minutos(fim):
        raise HTTPException(422, "a janela precisa começar antes de terminar")


def _hora_valida(v: object) -> bool:
    if not isinstance(v, str):
        return False
    try:
        h, m = v.split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59 and len(m) == 2
    except Exception:
        return False


def _minutos(v: str) -> int:
    h, m = v.split(":")
    return int(h) * 60 + int(m)


@router.get("/followup/previa")
def previa_followup(temperatura: str = Query("morno")):
    """Quando cada tentativa cairia, com a configuração salva — o painel mostra antes de o corretor confiar."""
    return {"temperatura": temperatura, "politica": politica_followup.politica(),
            "previa": politica_followup.previa(temperatura)}


@router.delete("/{chave}", status_code=204)
def restaurar(chave: str):
    """Volta a chave para os defaults."""
    if chave not in DEFAULTS:
        raise HTTPException(404)
    ConfigRepository().salvar(chave, {})
    if chave == "followup":
        politica_followup.invalidar_cache()
    if chave == "modelos":
        # Restaurar o padrão é o caminho de recuperação de um modelo ruim: tem que valer na hora,
        # senão o worker segue chamando o modelo quebrado com o override já apagado.
        from sdr_shared.db import invalidar_cache_modelos
        invalidar_cache_modelos()
    if chave == "operacao":
        from sdr_shared.db import invalidar_cache_operacao
        invalidar_cache_operacao()


@router.post("/modelos/testar")
def testar_modelo(body: dict):
    """Faz UMA chamada real e curta ao modelo pedido, antes de salvar.

    Lista fixa de modelos envelhece e campo livre derruba o agente no turno seguinte; um teste de
    verdade responde as duas dúvidas que a lista não responde — o ID existe neste provedor e nesta
    região? e quanto ele demora? Também avisa se falta preço, porque salvar sem preço desliga o
    teto de orçamento em dólar (ver _validar_modelos).
    """
    import time

    from sdr_shared.db import UsoRepository
    from sdr_shared.governanca import preco_do_modelo
    from sdr_shared.ports.factory import _construir

    modelo = (body.get("modelo") or "").strip()
    provider = (body.get("provider") or "").strip() or get_settings().llm_provider
    if not modelo:
        raise HTTPException(422, "informe o modelo a testar")
    if provider not in PROVIDERS or not provider:
        raise HTTPException(422, f"provedor desconhecido '{provider}'")

    preco = preco_do_modelo(modelo, UsoRepository().precos())
    inicio = time.perf_counter()
    try:
        # papel="roteamento" → temperatura 0; prompt mínimo, para o teste custar praticamente nada
        resposta = _construir(provider, modelo, 0.0, "roteamento").invoke("Responda apenas: ok")
        ms = int((time.perf_counter() - inicio) * 1000)
        texto = getattr(resposta, "content", str(resposta))
        return {"ok": True, "latencia_ms": ms, "resposta": str(texto)[:120],
                "tem_preco": bool(preco), "preco": list(preco) if preco else None}
    except Exception as e:
        return {"ok": False, "latencia_ms": int((time.perf_counter() - inicio) * 1000),
                "erro": f"{type(e).__name__}: {e}"[:300], "tem_preco": bool(preco),
                "preco": list(preco) if preco else None}
