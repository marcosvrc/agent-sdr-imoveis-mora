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


def test_sem_bucket_e_uma_simulacao(pasta, capsys):
    """O perfil local não tem Knowledge Base: rodar aqui tem de listar e sair bem, não estourar."""
    assert ing.main(str(pasta)) == 0
    saida = capsys.readouterr().out
    assert "seco" in saida and "visitas/politica.md" in saida


def test_pasta_vazia_nao_e_erro(tmp_path, capsys):
    assert ing.main(str(tmp_path)) == 0
    assert "nenhum documento" in capsys.readouterr().out
