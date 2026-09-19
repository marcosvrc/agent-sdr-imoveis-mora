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
    python -m sdr_ingestion.ingest_documentos data/documentos            # local: indexa no pgvector

Sem bucket (perfil local) o script NÃO faz mais uma listagem seca: ele fatia, gera embeddings e
grava na tabela `documentos`, que é de onde o agente lê. Enquanto era só listagem, a base
institucional existia no papel e o agente não tinha o que consultar — os documentos eram ingeridos
para lugar nenhum. Use `--seco` para voltar a só listar.
"""
import json
import sys
from pathlib import Path

EXTENSOES = {".md", ".txt", ".html", ".pdf"}     # o que a Knowledge Base sabe ler
MAX_MB = 45                                      # limite prático por arquivo na KB
# O que o fatiador local sabe ler. PDF e HTML exigiriam extrator e ficam só no caminho da KB —
# melhor recusar explicitamente do que indexar o binário como se fosse texto.
TEXTO_LOCAL = {".md", ".txt"}


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


def indexar_local(arquivos: list[Path], raiz: Path) -> int:
    """Fatia, gera embeddings e grava na tabela `documentos` (perfil local, sem Knowledge Base).

    Apaga os trechos antigos de cada arquivo ANTES de gravar os novos. Sem isso, editar o FAQ e
    remover uma pergunta deixa o trecho revogado no banco para sempre — e o agente segue
    respondendo com a política antiga, que é o pior tipo de dado velho: o que ninguém sabe que
    ainda está lá.

    Mas o apagar só acontece depois que TODOS os embeddings do arquivo foram gerados. A ordem
    importa: gerar embedding é a parte que depende de serviço externo (Ollama, Bedrock) e é a que
    falha. Apagando primeiro e embedando em seguida, um Ollama parado no meio do arquivo deixava a
    base com MENOS trechos do que antes de rodar — uma reindexação que destrói em vez de atualizar.
    Agora, se o embedder cair, nada foi apagado e o estado anterior continua de pé.
    """
    from sdr_shared.conhecimento import fatiar
    from sdr_shared.db import DocumentoRepository
    from sdr_shared.ports import get_embedder

    repo, embedder, total = DocumentoRepository(), get_embedder(), 0
    for a in arquivos:
        if a.suffix.lower() not in TEXTO_LOCAL:
            print(f"! {a.name}: {a.suffix} só é indexado pela Knowledge Base, não localmente",
                  file=sys.stderr)
            continue
        nome = a.relative_to(raiz).as_posix()
        assunto = metadata(a, raiz)["metadataAttributes"]["assunto"]
        trechos = fatiar(a.read_text(encoding="utf-8"), nome, assunto)
        if not trechos:
            # Nenhum trecho aproveitável (arquivo só com cabeçalhos, corpo curto demais, formatação
            # que o fatiador não entende). Apagar aqui zeraria silenciosamente o que já estava
            # indexado deste arquivo: um "✓ 0 trecho(s)" que na verdade apagou a política inteira.
            # Esvaziar a base tem de ser um ato explícito, não efeito colateral de um parse vazio.
            print(f"! {nome}: nenhum trecho aproveitável — mantido o que já estava indexado",
                  file=sys.stderr)
            continue
        try:
            vetores = [embedder.embed(tr.texto) for tr in trechos]
        except Exception as e:
            # Sem traceback: quem roda isto quer saber o que ligar, não a pilha do botocore.
            raise SystemExit(
                f"✗ {nome}: falha ao gerar embeddings ({type(e).__name__}: {e}).\n"
                f"  Nada foi apagado — a base institucional continua como estava.\n"
                f"  No perfil local, confira se o Ollama está no ar (`ollama serve`) e se o modelo "
                f"de embedding foi baixado.") from e
        removidos = repo.apagar_do_arquivo(nome)
        for tr, vetor in zip(trechos, vetores, strict=True):
            repo.upsert(tr, vetor)
        total += len(trechos)
        print(f"  ✓ {nome}: {len(trechos)} trecho(s)"
              + (f" (substituindo {removidos})" if removidos else ""))
    return total


def main(pasta: str = "data/documentos", bucket: str | None = None,
         kb_id: str | None = None, ds_id: str | None = None, seco: bool = False) -> int:
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

    if seco:
        print(f"(seco) {len(arquivos)} documento(s) seriam processados:")
        for a in arquivos:
            print(f"  {a.relative_to(raiz).as_posix()}  assunto={metadata(a, raiz)['metadataAttributes']['assunto']}")
        return 0

    if not bucket:
        total = indexar_local(arquivos, raiz)
        print(f"✓ {total} trecho(s) indexados em `documentos` — a Mora já consulta daqui.")
        return 0

    for a in arquivos:
        print(f"  ✓ {para_s3(bucket, a, raiz)}")
    if kb_id and ds_id:
        sync_kb(kb_id, ds_id)
        print("  sincronização da Knowledge Base disparada (o job roda em background na AWS)")
    print(f"✓ {len(arquivos)} documento(s) enviados" + (f", {len(grandes)} ignorados" if grandes else ""))
    return 1 if grandes else 0


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if a != "--seco"]
    raise SystemExit(main(*argumentos, seco="--seco" in sys.argv))
