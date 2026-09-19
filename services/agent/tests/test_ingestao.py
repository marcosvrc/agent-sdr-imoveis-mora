"""Ingestão de documentos institucionais para a Knowledge Base.

O que se testa aqui é o CONTRATO com a KB — chave no S3, arquivo de metadado ao lado e o assunto
tirado da subpasta —, porque é isso que decide se a recuperação consegue filtrar depois. O envio em
si é `put_object`: dublê basta.
"""
import json
from pathlib import Path

import pytest

import sdr_ingestion.ingest_documentos as ing


class S3Falso:
    def __init__(self): self.objetos = {}
    def put_object(self, Bucket, Key, Body): self.objetos[Key] = Body       # noqa: N803 (assinatura do boto3)


@pytest.fixture
def pasta(tmp_path) -> Path:
    (tmp_path / "visitas").mkdir()
    (tmp_path / "visitas" / "politica.md").write_text("# Política de visita\nAcompanhada por corretor.", encoding="utf-8")
    (tmp_path / "taxas.md").write_text("# Taxas\nSem taxa de reserva.", encoding="utf-8")
    (tmp_path / "logo.png").write_bytes(b"nao-e-texto")
    return tmp_path


def test_so_sobe_o_que_a_kb_sabe_ler(pasta):
    nomes = {p.name for p in ing.coletar(str(pasta))}
    assert nomes == {"politica.md", "taxas.md"}, "imagem na pasta não vira documento"


def test_a_subpasta_vira_assunto(pasta):
    """`assunto` é o que permite recuperar a política de visita sem trazer a tabela de taxas junto."""
    assunto = lambda p: ing.metadata(p, pasta)["metadataAttributes"]["assunto"]  # noqa: E731
    assert assunto(pasta / "visitas" / "politica.md") == "visitas"
    assert assunto(pasta / "taxas.md") == "geral"


def test_cada_documento_sobe_com_o_metadado_ao_lado(pasta, monkeypatch):
    """Sem o `.metadata.json` irmão, a KB indexa o texto e perde o filtro — falha silenciosa: a busca
    funciona, só devolve o documento errado."""
    s3 = S3Falso()
    monkeypatch.setattr(ing, "para_s3", lambda bucket, arquivo, raiz: _subir(s3, bucket, arquivo, raiz))
    ing.main(str(pasta), "bucket-teste")

    assert set(s3.objetos) == {
        "documentos/taxas.md", "documentos/taxas.md.metadata.json",
        "documentos/visitas/politica.md", "documentos/visitas/politica.md.metadata.json"}
    meta = json.loads(s3.objetos["documentos/visitas/politica.md.metadata.json"])
    assert meta["metadataAttributes"] == {"documento": "politica", "assunto": "visitas", "formato": "md"}


def _subir(s3, bucket, arquivo, raiz):
    chave = f"documentos/{arquivo.relative_to(raiz).as_posix()}"
    s3.put_object(Bucket=bucket, Key=chave, Body=arquivo.read_bytes())
    s3.put_object(Bucket=bucket, Key=f"{chave}.metadata.json",
                  Body=json.dumps(ing.metadata(arquivo, raiz)).encode())
    return chave


def test_seco_lista_e_nao_toca_no_banco(pasta, capsys, monkeypatch):
    """`--seco` é a inspeção: mostra o que seria processado sem indexar nada."""
    monkeypatch.setattr(ing, "indexar_local", _nao_chamar)
    assert ing.main(str(pasta), seco=True) == 0
    saida = capsys.readouterr().out
    assert "seco" in saida and "visitas/politica.md" in saida


def test_pasta_vazia_nao_e_erro(tmp_path, capsys):
    assert ing.main(str(tmp_path)) == 0
    assert "nenhum documento" in capsys.readouterr().out


# --------------------------------------------------------- indexação local (perfil sem KB)

def _nao_chamar(*a, **k):
    raise AssertionError("não devia ter sido chamado")


class RepoFalso:
    def __init__(self): self.linhas, self.apagados = {}, []
    def apagar_do_arquivo(self, nome):
        self.apagados.append(nome)
        antes = len(self.linhas)
        self.linhas = {k: v for k, v in self.linhas.items() if not k.startswith(f"{nome}#")}
        return antes - len(self.linhas)
    def upsert(self, trecho, vetor): self.linhas[trecho.id] = vetor


def _montar(monkeypatch, repo, embed):
    """Liga o RepoFalso e um embedder dublê nos pontos que `indexar_local` importa lá dentro."""
    import sdr_shared.db as db
    import sdr_shared.ports as ports
    monkeypatch.setattr(db, "DocumentoRepository", lambda: repo)
    monkeypatch.setattr(ports, "get_embedder", lambda: type("E", (), {"embed": staticmethod(embed)})())


def test_indexa_os_trechos_do_arquivo(pasta, monkeypatch, capsys):
    repo = RepoFalso()
    _montar(monkeypatch, repo, lambda texto: [0.1] * 1024)
    assert ing.main(str(pasta)) == 0
    assert repo.linhas, "nada foi gravado"
    assert all("#" in ident for ident in repo.linhas)
    assert "indexados" in capsys.readouterr().out


def test_embedder_fora_do_ar_nao_esvazia_a_base(pasta, monkeypatch):
    """O defeito que este teste tranca: apagava-se o trecho antigo e só depois se gerava o embedding.

    Com o Ollama parado no meio do arquivo, a reindexação deixava a base com MENOS conteúdo do que
    tinha antes de rodar — o agente perdia a política que já sabia responder. Falhar sem apagar é a
    única saída aceitável: quem roda de novo amanhã ainda tem a versão de ontem.
    """
    repo = RepoFalso()
    repo.linhas["visitas/politica.md#0"] = [0.0] * 1024      # o que já estava indexado

    def embedder_caido(texto):
        raise RuntimeError("connection refused")
    _montar(monkeypatch, repo, embedder_caido)

    with pytest.raises(SystemExit) as erro:
        ing.main(str(pasta))

    assert repo.apagados == [], "apagou antes de saber se conseguiria reindexar"
    assert "visitas/politica.md#0" in repo.linhas, "a base ficou menor do que antes de rodar"
    mensagem = str(erro.value)
    assert "Nada foi apagado" in mensagem
    assert "connection refused" in mensagem, "a causa real tem de aparecer, não só o rótulo"


def test_arquivo_sem_trecho_aproveitavel_nao_apaga_o_que_ja_existia(tmp_path, monkeypatch, capsys):
    """Achado por acidente enquanto se testava o embedder caído, e é um caminho separado: aqui nada
    falha. O arquivo simplesmente não rende trecho nenhum (só cabeçalhos, ou corpo abaixo do mínimo),
    o `for` dos embeddings não roda, exceção nenhuma sobe — e o apagar seguia em frente, zerando a
    indexação anterior e imprimindo "✓ 0 trecho(s)" como se tivesse dado certo.
    """
    (tmp_path / "taxas.md").write_text("# Taxas\n\n## Reserva\n", encoding="utf-8")
    repo = RepoFalso()
    repo.linhas["taxas.md#0"] = [0.2] * 1024        # a versão boa, indexada ontem
    _montar(monkeypatch, repo, lambda texto: [0.1] * 1024)

    assert ing.main(str(tmp_path)) == 0
    assert repo.apagados == []
    assert "taxas.md#0" in repo.linhas, "esvaziou a indexação por causa de um arquivo vazio"
    assert "nenhum trecho aproveitável" in capsys.readouterr().err


def test_pdf_e_html_sao_recusados_no_caminho_local(tmp_path, monkeypatch, capsys):
    """A KB extrai texto de PDF; o fatiador local não. Indexar o binário como texto produziria
    trechos de lixo com embedding válido — ruído que a busca devolve com confiança."""
    (tmp_path / "contrato.pdf").write_bytes(b"%PDF-1.4 binario")
    (tmp_path / "taxas.md").write_text("# Taxas\nSem taxa de reserva.", encoding="utf-8")
    repo = RepoFalso()
    _montar(monkeypatch, repo, lambda texto: [0.1] * 1024)
    ing.main(str(tmp_path))
    assert all(ident.startswith("taxas.md") for ident in repo.linhas)
    assert "contrato.pdf" in capsys.readouterr().err
