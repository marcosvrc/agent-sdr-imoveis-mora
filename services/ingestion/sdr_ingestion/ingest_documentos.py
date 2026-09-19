"""
Documentos institucionais (FAQ, políticas, condições) → tabela `documentos` (pgvector).

Complementa a ingestão de imóveis (ADR-0001): o catálogo responde "que imóvel serve para mim", estes
documentos respondem "como vocês trabalham" — taxa, documentação necessária, política de visita,
prazo de resposta. É o que evita a Mora inventar regra de negócio quando o cliente pergunta.

Diferença que justifica um script separado: **chunking**. Imóvel é um arquivo = um chunk (a ficha
inteira é a unidade que faz sentido recuperar); documento é texto corrido e vai fatiado por seção,
em `sdr_shared.conhecimento.fatiar`.

Uso:
    python -m sdr_ingestion.ingest_documentos data/documentos
    python -m sdr_ingestion.ingest_documentos data/documentos --seco   # só lista o que faria
"""
import sys
from pathlib import Path

# Só texto: PDF e HTML exigiriam extrator próprio, e indexar o binário como se fosse texto encheria
# a base de lixo que o agente citaria como política da empresa. Recusar é mais honesto.
EXTENSOES = {".md", ".txt"}


def coletar(pasta: str) -> list[Path]:
    raiz = Path(pasta)
    if not raiz.is_dir():
        raise SystemExit(f"pasta não encontrada: {raiz}")
    return sorted(p for p in raiz.rglob("*") if p.is_file() and p.suffix.lower() in EXTENSOES)


def metadata(arquivo: Path, raiz: Path) -> dict:
    """`assunto` é a subpasta — é assim que se recupera só a política de visita sem trazer a tabela
    de taxas junto."""
    relativo = arquivo.relative_to(raiz)
    assunto = relativo.parts[0] if len(relativo.parts) > 1 else "geral"
    return {"documento": arquivo.stem, "assunto": assunto, "formato": arquivo.suffix.lstrip(".")}


def indexar_local(arquivos: list[Path], raiz: Path) -> int:
    """Fatia, gera embeddings e grava na tabela `documentos`.

    Apaga os trechos antigos de cada arquivo ANTES de gravar os novos. Sem isso, editar o FAQ e
    remover uma pergunta deixa o trecho revogado no banco para sempre — e o agente segue
    respondendo com a política antiga, que é o pior tipo de dado velho: o que ninguém sabe que
    ainda está lá.

    Mas o apagar só acontece depois que TODOS os embeddings do arquivo foram gerados. A ordem
    importa: gerar embedding é a parte que depende de serviço externo (o Ollama) e é a que falha.
    Apagando primeiro e embedando em seguida, um Ollama parado no meio do arquivo deixava a base
    com MENOS trechos do que antes de rodar — uma reindexação que destrói em vez de atualizar.
    Agora, se o embedder cair, nada foi apagado e o estado anterior continua de pé.
    """
    from sdr_shared.conhecimento import fatiar
    from sdr_shared.db import DocumentoRepository
    from sdr_shared.ports import get_embedder

    repo, embedder, total = DocumentoRepository(), get_embedder(), 0
    for a in arquivos:
        nome = a.relative_to(raiz).as_posix()
        assunto = metadata(a, raiz)["assunto"]
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
            # Sem traceback: quem roda isto quer saber o que ligar, não a pilha do cliente HTTP.
            raise SystemExit(
                f"✗ {nome}: falha ao gerar embeddings ({type(e).__name__}: {e}).\n"
                f"  Nada foi apagado — a base institucional continua como estava.\n"
                f"  Confira se o Ollama está no ar e se o modelo de embedding foi baixado "
                f"(`make ollama-pull`).") from e
        removidos = repo.apagar_do_arquivo(nome)
        for tr, vetor in zip(trechos, vetores, strict=True):
            repo.upsert(tr, vetor)
        total += len(trechos)
        print(f"  ✓ {nome}: {len(trechos)} trecho(s)"
              + (f" (substituindo {removidos})" if removidos else ""))
    return total


def main(pasta: str = "data/documentos", seco: bool = False) -> int:
    raiz = Path(pasta)
    arquivos = coletar(pasta)
    if not arquivos:
        print(f"nenhum documento em {raiz} (extensões aceitas: {', '.join(sorted(EXTENSOES))})")
        return 0

    if seco:
        print(f"(seco) {len(arquivos)} documento(s) seriam processados:")
        for a in arquivos:
            print(f"  {a.relative_to(raiz).as_posix()}  assunto={metadata(a, raiz)['assunto']}")
        return 0

    total = indexar_local(arquivos, raiz)
    print(f"✓ {total} trecho(s) indexados em `documentos` — a Mora já consulta daqui.")
    return 0


if __name__ == "__main__":
    argumentos = [a for a in sys.argv[1:] if a != "--seco"]
    raise SystemExit(main(*argumentos, seco="--seco" in sys.argv))
