"""Política de follow-up: quando a Mora volta a falar com quem sumiu.

Três decisões vivem aqui, e todas são configuráveis pelo painel (chave `followup` da tabela
`configuracoes`; os valores abaixo são o padrão quando nada foi salvo):

  1. a cadência — quantas tentativas e de quanto em quanto tempo;
  2. o ritmo por temperatura — quem estava quente e sumiu merece um retorno mais rápido que
     quem mal conversou, do mesmo jeito que um SDR humano prioriza;
  3. a janela civilizada — ninguém recebe mensagem de imobiliária às duas da manhã.

O cálculo devolve SEMPRE minutos a partir de agora, porque é o que as duas implementações de
scheduler (Postgres local e EventBridge na AWS) entendem.
"""
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

FUSO = ZoneInfo("America/Sao_Paulo")      # o cliente vive neste fuso, não em UTC

PADRAO = {
    # Uma entrada por tentativa, em minutos desde o fim da conversa. Mexer no tamanho da lista
    # muda o número de tentativas — não há "3" escondido em lugar nenhum.
    "tempos_min": [120, 1440, 4320],          # 2h, 24h, 72h
    # Multiplicador sobre o tempo, por temperatura do lead no momento de agendar.
    "ritmo": {"quente": 0.25, "morno": 1.0, "frio": 2.0},
    "janela_inicio": "08:00",
    "janela_fim": "20:00",
    "dias_uteis": False,                       # True = não manda sábado nem domingo
    "ativo": True,
}
MIN_DELAY = 5           # nunca agenda para "daqui a nada": o cliente acabou de escrever


def _hora(texto: str, queda: str) -> tuple[int, int]:
    try:
        h, m = str(texto).split(":")
        return max(0, min(23, int(h))), max(0, min(59, int(m)))
    except Exception:
        h, m = queda.split(":")
        return int(h), int(m)


# Formato anterior da tela (três tempos fixos, em unidades diferentes). Convertido na leitura e na
# gravação, para que uma configuração salva antes não vire erro nem volte ao padrão sem avisar.
LEGADO = ("primeiro_min", "segundo_h", "terceiro_h", "maximo")


def migrar(salva: dict) -> dict:
    """Traduz a configuração antiga para a atual. Sem campos legados, devolve o que recebeu."""
    if not any(k in salva for k in LEGADO):
        return dict(salva)
    novo = {k: v for k, v in salva.items() if k not in LEGADO}
    if "tempos_min" not in novo:
        tempos = [salva.get("primeiro_min", 120),
                  int(salva.get("segundo_h", 24)) * 60,
                  int(salva.get("terceiro_h", 72)) * 60]
        maximo = salva.get("maximo")
        if isinstance(maximo, int) and 0 < maximo < len(tempos):
            tempos = tempos[:maximo]           # "máximo de tentativas" virou o tamanho da lista
        novo["tempos_min"] = [int(t) for t in tempos if isinstance(t, (int, float)) and t > 0]
    return novo


def politica() -> dict:
    """Config salva pelo painel, mesclada com o padrão. Campos inválidos caem no padrão."""
    from .db.painel import ConfigRepository
    try:
        salva = migrar(ConfigRepository().todas().get("followup") or {})
    except Exception:                          # banco indisponível não pode derrubar o turno
        salva = {}
    p = {**PADRAO, **{k: v for k, v in salva.items() if k in PADRAO}}
    tempos = [int(t) for t in (p.get("tempos_min") or []) if isinstance(t, (int, float)) and t > 0]
    p["tempos_min"] = tempos or list(PADRAO["tempos_min"])
    p["ritmo"] = {**PADRAO["ritmo"], **(p.get("ritmo") or {})}
    return p


_cache: dict = {"em": 0.0, "valor": None}


def politica_cacheada(segundos: float = 60) -> dict:
    """Caminho quente: todo turno consulta isto. 60s é tempo de o painel parecer instantâneo."""
    if _cache["valor"] is not None and time.time() - _cache["em"] < segundos:
        return _cache["valor"]
    v = politica()
    _cache.update(em=time.time(), valor=v)
    return v


def invalidar_cache() -> None:
    _cache.update(em=0.0, valor=None)


def dentro_da_janela(quando: datetime, p: dict | None = None) -> bool:
    p = p or politica_cacheada()
    local = quando.astimezone(FUSO)
    if p.get("dias_uteis") and local.weekday() >= 5:
        return False
    ini_h, ini_m = _hora(p.get("janela_inicio"), PADRAO["janela_inicio"])
    fim_h, fim_m = _hora(p.get("janela_fim"), PADRAO["janela_fim"])
    minutos = local.hour * 60 + local.minute
    return ini_h * 60 + ini_m <= minutos < fim_h * 60 + fim_m


def proximo_horario_valido(quando: datetime, p: dict | None = None) -> datetime:
    """Empurra para a próxima abertura da janela. Adiar é melhor que calar: a conversa continua,
    só não no meio da madrugada."""
    p = p or politica_cacheada()
    ini_h, ini_m = _hora(p.get("janela_inicio"), PADRAO["janela_inicio"])
    local = quando.astimezone(FUSO)
    for _ in range(8):                          # no máximo uma semana à frente
        if dentro_da_janela(local, p):
            return local
        fim_h, fim_m = _hora(p.get("janela_fim"), PADRAO["janela_fim"])
        passou_do_fim = (local.hour, local.minute) >= (fim_h, fim_m)
        antes_da_abertura = (local.hour, local.minute) < (ini_h, ini_m)
        dia = local if (antes_da_abertura and not passou_do_fim) else local + timedelta(days=1)
        local = dia.replace(hour=ini_h, minute=ini_m, second=0, microsecond=0)
    return local


def calcular(tentativas_feitas: int, temperatura: str = "morno", agora: datetime | None = None) -> int | None:
    """Minutos até o próximo follow-up, ou None quando não há mais o que fazer.

    None significa fim de linha: as tentativas acabaram ou o follow-up está desligado.
    """
    p = politica_cacheada()
    if not p.get("ativo", True):
        return None
    tempos = p["tempos_min"]
    if tentativas_feitas >= len(tempos):
        return None

    base = tempos[tentativas_feitas] * float(p["ritmo"].get(str(temperatura), 1.0))
    agora = agora or datetime.now(FUSO)
    alvo = proximo_horario_valido(agora.astimezone(FUSO) + timedelta(minutes=base), p)
    return max(MIN_DELAY, int((alvo - agora.astimezone(FUSO)).total_seconds() // 60))


def previa(temperatura: str = "morno", agora: datetime | None = None) -> list[dict]:
    """Quando cairia cada tentativa, para o painel mostrar antes de salvar."""
    p = politica_cacheada()
    agora = (agora or datetime.now(FUSO)).astimezone(FUSO)
    momento, saida = agora, []
    for i in range(len(p["tempos_min"])):
        minutos = calcular(i, temperatura, momento)
        if minutos is None:
            break
        momento = momento + timedelta(minutes=minutos)
        saida.append({"tentativa": i + 1, "minutos": minutos, "em": momento.isoformat()})
    return saida
