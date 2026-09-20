"""Escolha de modelo por nível, editável no painel (ADR-0010).

Antes, modelo era só variável de ambiente: trocar exigia redeploy. Agora a chave `modelos` da tabela
`configuracoes` manda, e o `.env` fica como piso — campo vazio no painel significa "usa o do ambiente".
Assim uma configuração ruim se desfaz apagando o override (DELETE /config/modelos), sem acesso ao banco.

Cache curto pelo mesmo motivo do orçamento: isto é lido em toda chamada de LLM e não pode virar um
SELECT por turno. `invalidar_cache_modelos()` é chamado ao salvar, para a troca valer na hora.
"""
import time

NIVEIS = ("conversa", "roteamento", "analise")

_cache: dict = {"em": 0.0, "valor": None}


def _do_banco() -> dict:
    from .painel import ConfigRepository
    try:
        return ConfigRepository().todas().get("modelos", {}) or {}
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return {}


def escolha(nivel: str, cache_segundos: float = 30) -> tuple[str | None, str | None]:
    """Devolve (modelo, provider) do painel para este nível — None onde o painel não opinou.

    `analise` cai em `conversa` quando não configurado: é o comportamento de hoje (o resumidor usa
    o modelo de conversa) e evita obrigar a preencher três níveis para mudar um.
    """
    if _cache["valor"] is None or time.time() - _cache["em"] > cache_segundos:
        _cache.update(em=time.time(), valor=_do_banco())
    cfg = _cache["valor"] or {}
    modelo = (cfg.get(nivel) or "").strip() or None
    provider = (cfg.get(f"{nivel}_provider") or "").strip() or None
    if nivel == "analise" and not modelo:
        return escolha("conversa", cache_segundos)
    return modelo, provider


def reserva(cache_segundos: float = 30) -> str | None:
    """Provedor de reserva escolhido no painel, ou None quando ele não opinou.

    Estava só no `.env`, e isso era uma assimetria estranha: dava para apontar o nível de conversa
    para outro provedor pela tela, mas não dava para dizer quem assume quando ele cai — justamente
    a decisão que alguém quer tomar com o sistema no ar, e não num arquivo que exige recriar
    container. Mesmo contrato dos níveis: vazio aqui significa "usa o do ambiente".
    """
    if _cache["valor"] is None or time.time() - _cache["em"] > cache_segundos:
        _cache.update(em=time.time(), valor=_do_banco())
    escolhido = ((_cache["valor"] or {}).get("fallback_provider") or "").strip()
    # "nenhum" é DESLIGAR pela tela, e precisa ser distinguível de "não opinei": sem isso, apagar o
    # campo no painel nunca desfaria um fallback que veio do ambiente.
    if escolhido == "nenhum":
        return "nenhum"
    return escolhido or None


def invalidar_cache_modelos() -> None:
    _cache.update(em=0.0, valor=None)
