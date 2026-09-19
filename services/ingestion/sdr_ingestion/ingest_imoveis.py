"""
Um chunk por imóvel (ADR-0001):
  1. grava o registro relacional no Postgres/Aurora (dashboard, filtros, API pública) COM embedding (busca híbrida pgvector);
  2. perfil aws: escreve `imoveis/<id>.txt` + `<id>.txt.metadata.json` no S3 e dispara sync da Knowledge Base.
Uso: python -m sdr_ingestion.ingest_imoveis data/imoveis/imoveis.json [bucket] [kb_id] [ds_id]

Com CRM configurado o registro comercial vem de lá e o arquivo entra só com os dados de vitrine
(ver `acervo.py`). Nesse caso a ingestão também PURGA o que o CRM não lista mais — é o que impede
o agente de continuar oferecendo um imóvel vendido.
"""
import json
import sys
import time

from sdr_shared.db import ImovelRepository
from sdr_shared.models import Imovel

from .acervo import carregar

# Um imóvel que ENTRA agora pode virar aviso para quem estava esperando por algo assim (fase 3 da
# reativação). Mas só um punhado por execução: uma rodada que insere dezenas é carga de catálogo,
# não novidade, e avisar a base inteira sobre ela é exatamente o disparo em massa que a reativação
# existe para não ser. Acima deste limite a ingestão grava tudo e não anuncia nada.
LIMITE_AVISOS_POR_LOTE = 5


def embed(texto: str) -> list[float]:
    from sdr_shared.ports import get_embedder
    return get_embedder().embed(texto)


def para_s3(bucket: str, im: Imovel) -> None:
    import boto3
    s3 = boto3.client("s3")
    meta = im.metadata()
    meta["metadataAttributes"] |= {"imovel_id": im.id, "titulo": f"{im.tipo.capitalize()} {im.quartos}q em {im.bairro}",
                                   "foto": im.fotos[0] if im.fotos else ""}
    s3.put_object(Bucket=bucket, Key=f"imoveis/{im.id}.txt", Body=im.texto_canonico().encode())
    s3.put_object(Bucket=bucket, Key=f"imoveis/{im.id}.txt.metadata.json", Body=json.dumps(meta).encode())


def sync_kb(kb_id: str, ds_id: str) -> None:
    import boto3
    boto3.client("bedrock-agent").start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)


def anunciar(novos: list[str]) -> None:
    """Publica `imovel-novo` para o reativador. Best-effort: falhar aqui não pode desfazer a carga."""
    if not novos:
        return
    if len(novos) > LIMITE_AVISOS_POR_LOTE:
        print(f"  ({len(novos)} imóveis novos nesta rodada — carga de catálogo, nenhum aviso enviado)")
        return
    try:
        from agent.reativador import publicar_imovel_novo
    except ImportError:                              # ingestão rodando sem o pacote do agente instalado
        print("  (pacote do agente indisponível: avisos de imóvel novo não publicados)", file=sys.stderr)
        return
    for imovel_id in novos:
        try:
            publicar_imovel_novo(imovel_id)
        except Exception as e:
            print(f"! {imovel_id}: não consegui publicar o aviso de imóvel novo ({type(e).__name__}: {e})", file=sys.stderr)
    print(f"  {len(novos)} imóvel(is) novo(s) anunciado(s) para a reativação: {', '.join(novos)}")


def main(caminho: str, bucket: str | None = None, kb_id: str | None = None, ds_id: str | None = None,
         avisar: bool = True) -> int:
    imoveis, do_crm = carregar(caminho)
    repo, t0, erros = ImovelRepository(), time.perf_counter(), 0
    novos: list[str] = []
    for i, im in enumerate(imoveis, 1):
        try:
            vec = embed(im.texto_canonico())
        except Exception as e:                       # Ollama fora / modelo não baixado: grava sem embedding e avisa
            erros += 1
            print(f"! {im.id}: embedding falhou ({type(e).__name__}: {e}); gravado sem vetor", file=sys.stderr)
            vec = None
        if repo.upsert(im, vec):
            novos.append(im.id)
        if bucket:
            para_s3(bucket, im)
        if i % 25 == 0 or i == len(imoveis):
            print(f"  {i}/{len(imoveis)} imóveis gravados ({time.perf_counter() - t0:.0f}s)")
    # Purga só quando a fonte é autoritativa: o CRM acabou de listar o acervo inteiro, então o que
    # não está nele saiu de circulação. Com o arquivo como fonte não se apaga nada — ele pode ser um
    # recorte, e um recorte não autoriza esvaziar o catálogo.
    if do_crm and imoveis:
        saidos = repo.apagar_fora_de([im.id for im in imoveis])
        if saidos:
            print(f"  {saidos} imóvel(is) saíram do índice (não estão mais disponíveis no CRM)")

    if kb_id and ds_id:
        sync_kb(kb_id, ds_id)
    if avisar:
        anunciar(novos)
    total, com_vetor = repo.contar(), repo.contar_com_embedding()
    print(f"✓ {total} imóveis no banco, {com_vetor} com embedding" + (f" — {erros} sem vetor (rode `make ollama-pull` e repita)" if erros else ""))
    return 0 if erros == 0 else 1


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--sem-avisos"]
    raise SystemExit(main(*args, avisar="--sem-avisos" not in sys.argv))
