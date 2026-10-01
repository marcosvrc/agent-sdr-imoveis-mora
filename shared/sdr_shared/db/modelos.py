"""Escolha de modelo por nível, editável no painel (ADR-0010).

Antes, modelo era só variável de ambiente: trocar exigia redeploy. Agora a chave `modelos` da tabela
`configuracoes` manda, e o `.env` fica como piso — campo vazio no painel significa "usa o do ambiente".
Assim uma configuração ruim se desfaz apagando o override (DELETE /config/modelos), sem acesso ao banco.

Cache curto pelo mesmo motivo do orçamento: isto é lido em toda chamada de LLM e não pode virar um
SELECT por turno. `invalidar_cache_modelos()` é chamado ao salvar, para a troca valer na hora.
"""
import time

from ..papeis import HERDA, PAPEIS

NIVEIS = PAPEIS                             # a lista mora em sdr_shared.papeis; aqui só o nome antigo

_cache: dict = {"em": 0.0, "valor": None}


def _do_banco() -> dict:
    from .painel import ConfigRepository
    try:
        return ConfigRepository().todas().get("modelos", {}) or {}
    except Exception:                       # sem banco (testes, boot): o ambiente decide sozinho
        return {}


def escolha(nivel: str, cache_segundos: float = 30, herdar: bool = True) -> tuple[str | None, str | None]:
    """Devolve (modelo, provider) do painel para este nível — None onde o painel não opinou.

    Papel vazio herda do pai (`sdr_shared.papeis.HERDA`): `analise` e `informacoes` caem em
    `conversa`, `extracao` cai em `roteamento`. Evita obrigar a preencher cinco campos para mudar um,
    e é o que mantém o comportamento de antes da divisão enquanto ninguém mexer nos papéis novos.
    `herdar=False` devolve só o que o painel diz para ESTE papel — é o que o factory usa para
    intercalar painel e ambiente nível a nível (ver `ports.factory.modelo_efetivo`).
    """
    if _cache["valor"] is None or time.time() - _cache["em"] > cache_segundos:
        _cache.update(em=time.time(), valor=_do_banco())
    cfg = _cache["valor"] or {}
    modelo = (cfg.get(nivel) or "").strip() or None
    provider = (cfg.get(f"{nivel}_provider") or "").strip() or None
    if herdar and not modelo and nivel in HERDA:
        return escolha(HERDA[nivel], cache_segundos)
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
