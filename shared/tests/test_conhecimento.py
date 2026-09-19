"""RAG institucional: fatiamento, piso de similaridade e recuperação contra pgvector real.

Uma ressalva honesta sobre o que este arquivo prova e o que não prova. O embedder de verdade
(bge-m3 no Ollama) não existe neste ambiente, então a recuperação é exercitada com um embedder
determinístico de saco-de-palavras. Isso **prova o encanamento** — fatiamento, SQL vetorial, ordem
por similaridade, piso, e o caminho de "não sei" — e **não prova a qualidade semântica**, que
depende do modelo real e precisa ser conferida com uma pergunta de verdade no ambiente local.

Dizer isso em voz alta importa: um teste verde aqui não autoriza afirmar que a busca institucional
"funciona bem", só que ela funciona.
"""
import hashlib
import os

import pytest

from sdr_shared.conhecimento import MAX_CHARS, PISO_SIMILARIDADE, Trecho, acima_do_piso, fatiar

DSN = os.environ.get("SDR_DATABASE_DSN", "")
precisa_banco = pytest.mark.skipif(
    not DSN or "test" not in DSN.rsplit("/", 1)[-1],
    reason="exige SDR_DATABASE_DSN apontando para um banco de teste")

DIM = 1024


def embedder_lexical(texto: str) -> list[float]:
    """Saco de palavras projetado em 1024 dimensões, normalizado.

    Não é semântico: "fiador" e "avalista" ficam distantes, onde um modelo real os aproximaria. Mas
    é determinístico e reproduz a propriedade que o teste precisa — vocabulário em comum aproxima,
    vocabulário disjunto afasta —, que é o suficiente para exercitar o piso e a ordenação.
    """
    import math
    vetor = [0.0] * DIM
    palavras = [p for p in "".join(c.lower() if c.isalnum() else " " for c in texto).split()
                if len(p) > 3]
    for p in palavras:
        i = int(hashlib.sha256(p.encode()).hexdigest()[:8], 16) % DIM
        vetor[i] += 1.0
    norma = math.sqrt(sum(x * x for x in vetor)) or 1.0
    return [x / norma for x in vetor]


# --------------------------------------------------------------------------- fatiamento

FAQ = """# Locação — garantias

Nota de contexto do documento, com tamanho suficiente para virar o trecho zero e não ser descartada.

## Preciso de fiador?

Não necessariamente. Fiador é uma das três garantias aceitas.

## Aceitam pets?

Depende do condomínio de cada imóvel.
"""


def test_fatia_por_cabecalho_e_nao_por_tamanho():
    trechos = fatiar(FAQ, "garantias.md", "locacao")
    titulos = [t.titulo for t in trechos]
    assert "Preciso de fiador?" in titulos
    assert "Aceitam pets?" in titulos
    # Cada pergunta é um trecho: a resposta não pode chegar partida ao meio.
    fiador = next(t for t in trechos if t.titulo == "Preciso de fiador?")
    assert "três garantias" in fiador.texto


def test_a_nota_de_contexto_nao_se_perde():
    """É onde mora o aviso de que o documento é de exemplo — perder isso é perder a ressalva.

    Num documento que começa por um título (o caso normal), a nota fica no trecho DESSE título, e
    não num trecho sem dono. Foi o que o código já fazia e o que este teste inicialmente negava —
    a expectativa estava errada, não a implementação.
    """
    trechos = fatiar(FAQ, "garantias.md", "locacao")
    assert trechos[0].titulo == "Locação — garantias"
    assert "Nota de contexto" in trechos[0].texto


def test_texto_antes_de_qualquer_cabecalho_vira_o_trecho_zero():
    sem_titulo = ("Aviso: documento institucional de exemplo, com texto solto no topo e tamanho "
                  "suficiente para contar.\n\n## Uma pergunta\n\nUma resposta qualquer aqui.")
    trechos = fatiar(sem_titulo, "d.md", "geral")
    assert trechos[0].titulo is None
    assert "Aviso" in trechos[0].texto


def test_o_cabecalho_vai_junto_em_cada_trecho():
    """Sem isso, o trecho recuperado chega ao modelo sem dizer de que assunto trata."""
    fiador = next(t for t in fatiar(FAQ, "g.md", "locacao") if t.titulo == "Preciso de fiador?")
    assert fiador.texto.startswith("Preciso de fiador?")


def test_secao_longa_e_dividida_com_o_cabecalho_repetido():
    longo = "## Taxas\n\n" + "\n\n".join(["Parágrafo com algum conteúdo de tamanho médio."] * 60)
    partes = fatiar(longo, "taxas.md", "geral")
    assert len(partes) > 1
    assert all(len(p.texto) <= MAX_CHARS + 200 for p in partes)
    assert all(p.titulo == "Taxas" for p in partes)
    assert all(p.texto.startswith("Taxas") for p in partes)


def test_ids_sao_estaveis_entre_reingestoes():
    """Reingerir o mesmo arquivo tem de atualizar as linhas, não criar cópias."""
    a = [t.id for t in fatiar(FAQ, "garantias.md", "locacao")]
    b = [t.id for t in fatiar(FAQ, "garantias.md", "locacao")]
    assert a == b and len(set(a)) == len(a)


def test_cabecalho_sem_corpo_nao_vira_trecho_vazio():
    doc = "# Título\n\n## Seção que só agrupa\n\n### Subseção\n\nConteúdo de verdade, com tamanho."
    trechos = fatiar(doc, "d.md", "geral")
    assert all(t.texto.strip() for t in trechos)
    assert [t.titulo for t in trechos] == ["Subseção"]


# --------------------------------------------------------------------------- piso

def test_piso_descarta_o_vizinho_mais_proximo_quando_ele_esta_longe():
    """A falha clássica de RAG: a busca sempre devolve algo, mesmo sem nada relevante."""
    perto = Trecho("a", "f.md", "geral", "T", "texto", 0, score=0.61)
    longe = Trecho("b", "f.md", "geral", "T", "texto", 1, score=0.12)
    assert acima_do_piso([perto, longe]) == [perto]
    assert acima_do_piso([longe]) == []


def test_piso_e_generoso_de_proposito():
    """Errar para 'não sei' custa uma pergunta; errar para o outro lado custa informação falsa."""
    assert 0.2 <= PISO_SIMILARIDADE <= 0.5


# --------------------------------------------------------------------------- recuperação real

@pytest.fixture
def base(limpo=None):
    from sdr_shared.db import DocumentoRepository
    repo = DocumentoRepository()
    for arquivo, assunto, conteudo in [
        ("garantias.md", "locacao", FAQ),
        ("taxas.md", "financeiro",
         "## Taxa de administração\n\nDez por cento do aluguel, descontada do repasse.\n"),
    ]:
        repo.apagar_do_arquivo(arquivo)
        for t in fatiar(conteudo, arquivo, assunto):
            repo.upsert(t, embedder_lexical(t.texto))
    return repo


@precisa_banco
def test_recupera_o_trecho_do_assunto_perguntado(base):
    achados = base.buscar(embedder_lexical("preciso de fiador para alugar?"), limite=3)
    assert achados
    assert achados[0].titulo == "Preciso de fiador?"
    # E o score vem junto: é sobre ele que o piso decide.
    assert achados[0].score > achados[-1].score or len(achados) == 1


@precisa_banco
def test_pergunta_sem_cobertura_nao_passa_do_piso(base):
    """A pergunta que o corpus não responde. Sem piso, a busca devolveria o trecho de taxas e o
    agente afirmaria algo sobre um assunto que nunca foi documentado."""
    achados = base.buscar(embedder_lexical("vocês fazem seguro de automóvel e veículos pesados?"), limite=3)
    assert acima_do_piso(achados) == []


@precisa_banco
def test_filtro_por_assunto(base):
    achados = base.buscar(embedder_lexical("taxa administração repasse"), limite=3, assunto="financeiro")
    assert achados and all(t.assunto == "financeiro" for t in achados)


@precisa_banco
def test_reingerir_documento_editado_remove_o_trecho_revogado(base):
    """O pior dado velho é o que ninguém sabe que ficou: uma política revogada que o agente segue
    respondendo porque o trecho antigo continuou no banco."""
    from sdr_shared.conhecimento import fatiar as f
    antes = base.buscar(embedder_lexical("preciso de fiador para alugar?"), limite=3)
    assert any(t.titulo == "Preciso de fiador?" for t in antes)

    editado = "# Locação — garantias\n\n## Aceitam pets?\n\nDepende do condomínio de cada imóvel.\n"
    base.apagar_do_arquivo("garantias.md")
    for t in f(editado, "garantias.md", "locacao"):
        base.upsert(t, embedder_lexical(t.texto))

    depois = base.buscar(embedder_lexical("preciso de fiador para alugar?"), limite=5)
    assert not any(t.titulo == "Preciso de fiador?" for t in depois)
