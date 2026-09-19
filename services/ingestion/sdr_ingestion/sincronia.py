"""Reindexação incremental do acervo, para rodar de tempos em tempos.

O problema que resolve: preço e status são do CRM, mas o agente busca no índice da Mora. Entre um
`make seed` e o seguinte, um imóvel vendido continua sendo oferecido — que é exatamente o que a
ligação com o CRM existe para impedir. Deixar isso na mão de alguém rodar um comando é deixar
descoberto o intervalo inteiro.

**Incremental, e não "roda o seed de novo".** Gerar embedding é a parte cara: com provedor
hospedado tem preço por token, com Ollama tem CPU. Reembedar 200 imóveis a cada quinze minutos para
descobrir que nenhum mudou é desperdício com as duas contas. Aqui o texto canônico do que está
indexado é comparado com o que veio do CRM, e só o que mudou (ou entrou agora) gera vetor novo. O
resto leva UPDATE dos campos comerciais com `embedding=None`, que o repositório preserva.

**A purga continua condicionada à fonte autoritativa.** Só um CRM que listou o acervo inteiro
autoriza apagar o que não está nele; leitura parcial levanta antes de chegar aqui (`acervo.py`), e
sem CRM configurado não se apaga nada.
"""
import logging

from sdr_shared.db import ImovelRepository

from .acervo import carregar

log = logging.getLogger("ingestao.sincronia")


def _indexados() -> dict[str, str]:
    """Texto canônico do que já está no índice, por id. Uma consulta só — são centenas de linhas."""
    from sdr_shared.db.connection import get_pool
    with get_pool().connection() as conn:
        linhas = conn.execute(
            f"SELECT {ImovelRepository.COLS} FROM imoveis WHERE embedding IS NOT NULL").fetchall()
    return {r["id"]: ImovelRepository._row(r).texto_canonico() for r in linhas}


def sincronizar(caminho: str) -> dict:
    """Uma passada. Devolve contagens; nunca levanta por falha de um imóvel."""
    imoveis, do_crm = carregar(caminho)
    if not do_crm:
        return {"fonte": "arquivo", "ignorado": True}

    repo, atual = ImovelRepository(), _indexados()
    novos, mudados, iguais, erros = 0, 0, 0, 0
    for im in imoveis:
        texto = im.texto_canonico()
        if atual.get(im.id) == texto:
            iguais += 1
            continue                       # nada mudou: nem UPDATE, nem embedding
        vetor = None
        try:
            from sdr_shared.ports import get_embedder
            vetor = get_embedder().embed(texto)
        except Exception:
            # Embedder fora do ar: grava os campos comerciais mesmo assim. Preço e status
            # atualizados sem vetor novo valem mais que nada — o vetor antigo ainda descreve o
            # imóvel, e o `COALESCE` do upsert o preserva.
            erros += 1
            log.warning("imóvel %s: embedding falhou; campos comerciais gravados sem vetor novo",
                        im.id, exc_info=True)
        if repo.upsert(im, vetor):
            novos += 1
        else:
            mudados += 1

    saidos = 0
    if imoveis:
        saidos = repo.apagar_fora_de([im.id for im in imoveis])
    return {"fonte": "crm", "total": len(imoveis), "novos": novos, "mudados": mudados,
            "sem_mudanca": iguais, "sem_vetor": erros, "saidos": saidos}
