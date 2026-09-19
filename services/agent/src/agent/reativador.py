"""Consumidor do tópico `imovel-novo`: entrou um imóvel, quem estava esperando por ele fica sabendo.

Este arquivo é só a **seleção e o disparo**. Ele não escreve mensagem nenhuma: para cada candidato
publica uma `MensagemNormalizada` do tipo REATIVACAO no tópico `inbound`, e daí em diante o turno é
um turno normal do agente — passa pelos guardrails, pelo orçamento, pela sanitização da saída, pela
auditoria e pelo registro em `turnos`. Escrever direto no canal daqui seria mais curto e deixaria a
única mensagem que a Mora manda sem ninguém ter pedido fora de todo o controle que existe no sistema.

A régua de quem recebe está em `sdr_shared.reativacao` e é a mesma que o painel simula em modo seco
(`GET /reativacao/imovel/{id}`): o corretor consegue ver antes o que sairia depois.
"""
import json
import logging

from sdr_shared.db import CanalRepository, ImovelRepository, InteresseRepository, LeadRepository, auditar
from sdr_shared.log import configurar as configurar_log
from sdr_shared.messaging import Canal, MensagemNormalizada, TipoMensagem
from sdr_shared.ports import get_broker
from sdr_shared.reativacao import avaliar

configurar_log("reativador")
log = logging.getLogger("agent.reativador")

MAX_LEADS = 500          # mesmo teto da simulação: acima disto a varredura vira trabalho de lote
MAX_AVISOS = 20          # teto por imóvel — um cadastro em massa não pode virar disparo em massa

# Por onde falar, quando o lead tem mais de um canal. Web fica de fora de propósito: o widget do
# site só existe enquanto a aba está aberta, então "avisar" ali é escrever para uma sala vazia.
#
# Hoje só há um canal assíncrono, então a tupla tem um elemento — e continua sendo uma tupla porque
# a ORDEM é a regra: quando entrar outro, o que decide é a posição aqui, não a ordem em que o lead
# se cadastrou nos canais.
PREFERENCIA = (Canal.TELEGRAM,)


def _melhor_canal(lead_id: str) -> tuple[Canal, str] | None:
    canais = {c["canal"]: c["identificador"] for c in CanalRepository().canais_do_lead(lead_id)}
    for canal in PREFERENCIA:
        if identificador := canais.get(str(canal.value)):
            return canal, identificador
    return None


def anunciar(imovel_id: str, limite: int = MAX_AVISOS) -> dict:
    """Avalia a base contra o imóvel novo e enfileira um turno de reativação por candidato."""
    im = ImovelRepository().get(imovel_id)
    if not im:
        log.warning("imóvel %s não existe mais — nada a anunciar", imovel_id)
        return {"imovel_id": imovel_id, "avisados": 0, "sem_canal": 0}

    leads = LeadRepository().listar(limite=MAX_LEADS)
    conhecidos = {l.id: InteresseRepository().por_situacao(l.id) for l in leads}
    resultado = avaliar(im, leads, conhecidos, limite=limite)
    por_id = {l.id: l for l in leads}

    avisados, sem_canal = 0, 0
    for candidato in resultado["candidatos"]:
        lead = por_id[candidato["lead_id"]]
        destino = _melhor_canal(lead.id)
        if not destino:
            # `elegivel` já exige telefone; isto é outra coisa: telefone cadastrado mas nenhuma
            # conversa aberta por onde escrever primeiro. Quem começa aí é o corretor, não a Mora.
            sem_canal += 1
            continue
        canal, identificador = destino
        entrada = MensagemNormalizada(
            lead_id=lead.id, canal=canal, identificador_canal=identificador,
            tipo=TipoMensagem.REATIVACAO, conteudo="",
            meta={"imovel_id": im.id, "motivos": candidato["motivos"], "pontos": candidato["pontos"]})
        get_broker().publish("inbound", entrada.model_dump_json(), key=lead.id)
        avisados += 1

    auditar(acao="reativacao.anunciada", entidade="imovel", entidade_id=im.id, ator_tipo="sistema",
            ator_nome="reativador", dados={"avaliados": resultado["avaliados"], "avisados": avisados,
                                           "sem_canal": sem_canal, "excluidos": len(resultado["excluidos"])})
    log.info("imóvel %s: %d avisos enfileirados de %d leads avaliados (%d sem canal)",
             im.id, avisados, resultado["avaliados"], sem_canal)
    return {"imovel_id": im.id, "avaliados": resultado["avaliados"], "avisados": avisados, "sem_canal": sem_canal}


def publicar_imovel_novo(imovel_id: str) -> None:
    """Chamado por quem cadastra imóvel (ingestão). Fica aqui, e não no repositório, para o
    `sdr_shared.db` continuar sem saber que existe fila."""
    get_broker().publish("imovel-novo", json.dumps({"imovel_id": imovel_id}), key=imovel_id)


def local_worker():
    from sdr_shared.db import iniciar_batimento

    iniciar_batimento("reativador")
    get_broker().consume("imovel-novo", lambda body: anunciar(json.loads(body)["imovel_id"]))
