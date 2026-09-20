"""Configurações do agente editáveis pelo painel. Defaults aqui; overrides na tabela `configuracoes`.

`followup` é lido pelo agente em tempo de execução (sdr_shared/followup.py) — salvar aqui muda o
comportamento no próximo turno. As demais chaves ainda são declarativas.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sdr_shared import followup as politica_followup
from sdr_shared.config import get_settings
from sdr_shared.db import ConfigRepository
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
    # Modelo por nível (ADR-0010). Vazio = usa o do .env, então dá para mexer em um nível só e
    # desfazer tudo com DELETE /config/modelos, sem precisar do banco.
    # `fallback_provider` vazio = usa o SDR_LLM_PROVIDER_FALLBACK do ambiente; a string "nenhum"
    # é o jeito de DESLIGAR o reserva pela tela sem mexer no .env. Sem ela, apagar o campo no
    # painel não conseguiria desfazer um fallback herdado do ambiente.
    "modelos": {"conversa": "", "conversa_provider": "", "roteamento": "", "roteamento_provider": "",
                "analise": "", "analise_provider": "", "fallback_provider": ""},
    # Ajustes de operação. Vazio = usa o do ambiente; um valor explícito (inclusive `0` e `off`)
    # é decisão de quem está olhando o sistema no ar. A distinção entre "vazio" e "desligado" é o
    # que permite a tela desfazer algo herdado do `.env` — ver db/operacao.py.
    "operacao": {"llm_timeout_s": "", "transcricao": "", "acervo_refresh_s": ""},
}

PROVIDERS = ("", "anthropic", "openai", "ollama")


def _modelos_efetivos() -> dict:
    """O que o agente realmente vai usar no próximo turno — a tela mostra isto, não a intenção."""
    from sdr_shared.db import escolha_de_modelo
    s = get_settings()
    saida = {}
    for nivel in ("conversa", "roteamento", "analise"):
        try:
            modelo, provider = escolha_de_modelo(nivel)
        except Exception:
            modelo, provider = None, None
        padrao = s.model_roteamento if nivel == "roteamento" else s.model_conversa
        saida[nivel] = {"modelo": modelo or padrao, "provider": provider or s.llm_provider,
                        "origem": "painel" if modelo else "ambiente"}
    return saida


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
                    "catalogo": _catalogo()},
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

    for nivel in ("conversa", "roteamento", "analise"):
        if (prov := body.get(f"{nivel}_provider")) and prov not in PROVIDERS:
            raise HTTPException(422, f"{nivel}_provider: provedor desconhecido '{prov}'")
        modelo = (body.get(nivel) or "").strip()
        if not modelo:
            continue
        if len(modelo) > 120 or any(c.isspace() for c in modelo):
            raise HTTPException(422, f"{nivel}: '{modelo}' não parece um identificador de modelo")
        # Ollama roda local e não tem custo; os demais precisam de preço para a governança funcionar
        if (body.get(f"{nivel}_provider") or "") == "ollama":
            continue
        if not preco_do_modelo(modelo, UsoRepository().precos()):
            raise HTTPException(422, f"{nivel}: sem preço cadastrado para '{modelo}'. Cadastre em "
                                     f"Configurações → preços antes de usá-lo, senão o custo é "
                                     f"contabilizado como zero e o teto de orçamento para de valer.")


def _validar_operacao(body: dict) -> None:
    """Cada um destes números tem uma faixa em que ele ainda é o que promete ser."""
    t = body.get("llm_timeout_s")
    if t not in (None, ""):
        if not isinstance(t, (int, float)) or not 5 <= t <= 180:
            raise HTTPException(422, "llm_timeout_s: entre 5 e 180 segundos. Abaixo de 5 o modelo "
                                     "não termina de responder; acima de 180 o cliente já desistiu.")
    tr = (body.get("transcricao") or "").strip()
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
    if ini and fim and _hora_valida(ini) and _hora_valida(fim) and ini >= fim:
        raise HTTPException(422, "a janela precisa começar antes de terminar")


def _hora_valida(v: object) -> bool:
    try:
        h, m = str(v).split(":")
        return 0 <= int(h) <= 23 and 0 <= int(m) <= 59 and len(m) == 2
    except Exception:
        return False


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
