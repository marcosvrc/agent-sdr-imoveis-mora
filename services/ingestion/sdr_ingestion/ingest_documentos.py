"""
Documentos institucionais (FAQ, políticas, condições) → S3 `documentos/` → Knowledge Base.

Complementa a ingestão de imóveis (ADR-0001): o catálogo responde "que imóvel serve para mim", estes
documentos respondem "como vocês trabalham" — taxa, documentação necessária, política de visita,
prazo de resposta. É o que evita a Mora inventar regra de negócio quando o cliente pergunta.

Diferença que justifica um script separado: **chunking**. Imóvel é um arquivo = um chunk (a ficha
inteira é a unidade que faz sentido recuperar); documento é texto corrido e vai hierárquico
(1500/300 tokens), configurado na data source `documentos` em `infra/stacks/ai_stack.py` — por isso
aqui não há código de chunking nenhum, só o envio e o metadado que permite filtrar.

Uso:
    python -m sdr_ingestion.ingest_documentos data/documentos [bucket] [kb_id] [ds_id]
    python -m sdr_ingestion.ingest_documentos data/documentos            # sem bucket: só lista (seco)

O perfil local não tem Knowledge Base: rodar sem bucket mostra o que subiria e sai sem erro, que é o
comportamento útil para conferir a pasta antes de um deploy.
"""
import json
import sys
from pathlib import Path

EXTENSOES = {".md", ".txt", ".html", ".pdf"}     # o que a Knowledge Base sabe ler
MAX_MB = 45                                      # limite prático por arquivo na KB


def coletar(pasta: str) -> list[Path]:
    raiz = Path(pasta)
    if not raiz.is_dir():
        raise SystemExit(f"pasta não encontrada: {raiz}")
    return sorted(p for p in raiz.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSOES)


def metadata(arquivo: Path, raiz: Path) -> dict:
    """Metadado para filtro na KB. `assunto` é a subpasta — é assim que se recupera só a política de
    visita sem trazer a tabela de taxas junto."""
    relativo = arquivo.relative_to(raiz)
    assunto = relativo.parts[0] if len(relativo.parts) > 1 else "geral"
    return {"metadataAttributes": {"documento": arquivo.stem, "assunto": assunto,
                                   "formato": arquivo.suffix.lstrip(".")}}


def para_s3(bucket: str, arquivo: Path, raiz: Path) -> str:
    import boto3
    s3 = boto3.client("s3")
    chave = f"documentos/{arquivo.relative_to(raiz).as_posix()}"
    s3.put_object(Bucket=bucket, Key=chave, Body=arquivo.read_bytes())
    s3.put_object(Bucket=bucket, Key=f"{chave}.metadata.json",
                  Body=json.dumps(metadata(arquivo, raiz)).encode())
    return chave


def sync_kb(kb_id: str, ds_id: str) -> None:
    import boto3
    boto3.client("bedrock-agent").start_ingestion_job(knowledgeBaseId=kb_id, dataSourceId=ds_id)


def main(pasta: str = "data/documentos", bucket: str | None = None,
         kb_id: str | None = None, ds_id: str | None = None) -> int:
    raiz = Path(pasta)
    arquivos = coletar(pasta)
    if not arquivos:
        print(f"nenhum documento em {raiz} (extensões aceitas: {', '.join(sorted(EXTENSOES))})")
        return 0

    # Arquivo grande demais é recusado pela KB no meio do job, com erro difícil de ligar à causa.
    # Melhor avisar aqui, nominalmente, e subir o resto.
    grandes = [a for a in arquivos if a.stat().st_size > MAX_MB * 1024 * 1024]
    for a in grandes:
        print(f"! {a}: {a.stat().st_size / 1024 / 1024:.0f} MB — acima do limite de {MAX_MB} MB, ignorado",
              file=sys.stderr)
    arquivos = [a for a in arquivos if a not in grandes]

    if not bucket:
        print(f"(seco — sem bucket) {len(arquivos)} documento(s) subiriam para `documentos/`:")
        for a in arquivos:
            print(f"  {a.relative_to(raiz).as_posix()}  assunto={metadata(a, raiz)['metadataAttributes']['assunto']}")
        return 0

    for a in arquivos:
        print(f"  ✓ {para_s3(bucket, a, raiz)}")
    if kb_id and ds_id:
        sync_kb(kb_id, ds_id)
        print("  sincronização da Knowledge Base disparada (o job roda em background na AWS)")
    print(f"✓ {len(arquivos)} documento(s) enviados" + (f", {len(grandes)} ignorados" if grandes else ""))
    return 1 if grandes else 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
