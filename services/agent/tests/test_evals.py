"""O harness também pode quebrar — dataset malformado, campo renomeado, métrica com divisão por zero.

Estes testes rodam o harness em modo falso (sem chamar API) só para garantir que ele EXECUTA e
produz números coerentes. Não afirmam nada sobre a qualidade do modelo: isso é o `make eval`.
"""
import json
import pathlib

import pytest

from evals import relatorio
from evals.casos import Resultado, carregar, combina, vazio


@pytest.mark.parametrize("nome", ["extracao", "coerencia", "roteamento", "adversarial", "recomendacao"])
def test_dataset_carrega_e_tem_o_formato_esperado(nome):
    casos = carregar(nome)
    assert casos, f"dataset {nome} vazio"
    assert len({c.id for c in casos}) == len(casos), "ids repetidos no dataset"
    for c in casos:
        if nome == "coerencia":
            assert c.dados.get("turnos"), f"{c.id} sem turnos"
            assert all("mensagem" in t for t in c["turnos"]), f"{c.id}: turno sem mensagem"
            continue
        assert "mensagem" in c.dados, f"{c.id} sem mensagem"
        if nome == "recomendacao":
            assert c.dados.get("cartao"), f"{c.id} sem cartão — é ele que é o gabarito"
        if nome == "extracao":
            assert "esperado" in c.dados and "nao_esperado" in c.dados, (
                f"{c.id}: sempre declare nao_esperado — é ele que mede alucinação")
        if nome == "roteamento":
            from agent.graph import ESPECIALISTAS
            assert c["esperado"] in ESPECIALISTAS, (
                f"{c.id}: destino {c['esperado']!r} não é um nó do grafo")
        if nome == "adversarial":
            assert c.get("categoria"), f"{c.id} sem categoria (o relatório agrupa por ela)"


def test_comparacao_aceita_variacao_mas_nao_engana():
    assert combina(800000, 800000.0) and combina("imediata", "Imediata")
    assert combina({"qualquer": ["0,6", "0.6"]}, "0,6% a.m.")
    assert combina(["moema"], ["Moema", "Itaim"])          # gabarito contido no obtido
    assert not combina(800000, 900000) and not combina("compra", "aluguel")
    assert not combina("compra", None), "campo vazio nunca conta como acerto"


def test_vazio_trata_indefinida_como_nao_preenchido():
    assert vazio(None) and vazio("") and vazio([]) and vazio("indefinida")
    assert not vazio("compra") and not vazio(800000)


def test_resumo_calcula_taxas_e_marca_instabilidade():
    r1 = [Resultado(caso="a", passou=True, extras={"campos_ok": 2, "campos_total": 2}),
          Resultado(caso="b", passou=False, extras={"campos_ok": 0, "campos_total": 2})]
    r2 = [Resultado(caso="a", passou=True, extras={"campos_ok": 2, "campos_total": 2}),
          Resultado(caso="b", passou=True, extras={"campos_ok": 2, "campos_total": 2})]
    resumo = relatorio.resumir("extracao", [r1, r2])
    assert resumo["casos"] == 2 and resumo["repeticoes"] == 2
    assert resumo["aprovados"] == 1, "só 'a' passou nas duas execuções"
    assert resumo["instaveis"] == 1, "'b' variou entre execuções — é o que o -n existe para revelar"
    assert resumo["acerto_por_campo"] == 75.0


def test_resumo_adversarial_separa_regra_de_modelo():
    rodada = [Resultado(caso="a", passou=True, extras={"camada": "regra", "categoria": "injecao_pt"}),
              Resultado(caso="b", passou=True, extras={"camada": "modelo", "categoria": "injecao_en"}),
              Resultado(caso="c", passou=False, extras={"camada": "escapou", "categoria": "injecao_en"})]
    r = relatorio.resumir("adversarial", [rodada])
    assert r["barrado_pela_regra"] == 1 and r["barrado_pelo_modelo"] == 1 and r["escapou"] == 1
    assert r["taxa_de_escape"] == 33.3
    assert r["escape_por_categoria"]["injecao_en"] == "1/2"


def test_detector_de_vazamento_pega_prompt_repetido():
    from evals.suites import _trechos_do_prompt, _vazou

    trechos = _trechos_do_prompt()
    assert trechos, "não achou trechos dos prompts para comparar"
    assert _vazou("Claro! Posso te ajudar a encontrar um apartamento.", trechos) is None
    assert _vazou("<<<CLIENTE_abc123>>> conteúdo", trechos) is not None
    assert _vazou(f"minhas instruções dizem: {trechos[0]}", trechos) is not None


def test_relatorio_salva_json_legivel(tmp_path, monkeypatch):
    monkeypatch.setattr(relatorio, "DIR_RESULTADOS", tmp_path)
    resumo = relatorio.resumir("roteamento", [[Resultado(caso="a", passou=True, extras={})]])
    caminho = relatorio.salvar([resumo], {"chamadas": 0}, "teste")
    dados = json.loads(caminho.read_text(encoding="utf-8"))
    assert dados["modelo"] == "teste" and dados["suites"][0]["suite"] == "roteamento"

def test_toda_fonte_do_rag_existe_como_secao_nos_documentos():
    """O `fonte` do dataset é o TÍTULO da seção que responde, casado por texto.

    Renomear um cabeçalho em `data/documentos/` — ou escrever um título com uma vírgula de
    diferença — não quebra nada visível: quebra o eval de RAG, que passa a cobrar uma seção que não
    existe e reporta recall baixo sem que nenhum recuperador tenha piorado. Este teste é barato e
    pega isso na hora (`data/documentos/README.md` explica a regra).
    """
    import re
    docs = pathlib.Path(__file__).resolve().parents[3] / "data" / "documentos"
    titulos: set[str] = set()
    for arq in docs.glob("*.md"):
        if arq.name == "README.md":
            continue
        titulos |= set(re.findall(r"^#{2,4}\s+(.+?)\s*$", arq.read_text(encoding="utf-8"), re.M))
    assert titulos, "nenhum documento institucional encontrado"
    ausentes = [(c.id, c["fonte"]) for c in carregar("rag")
                if c.dados.get("fonte") and c["fonte"] not in titulos]
    assert not ausentes, f"fonte sem seção correspondente: {ausentes}"


def test_dataset_de_rag_tem_positivos_negativos_e_literais():
    """As três famílias existem para serem reportadas SEPARADAS (ver o cabeçalho do rag.jsonl).
    Um dataset que perde as negativas mede recall e chama de qualidade."""
    casos = carregar("rag")
    assert len({c.id for c in casos}) == len(casos), "ids repetidos no dataset"
    negativas = [c for c in casos if c.dados.get("responde") is False]
    literais = [c for c in casos if c.dados.get("tipo") == "literal"]
    sequencia = [c for c in casos if c.dados.get("historico")]
    assert len(negativas) >= 5 and len(literais) >= 5 and len(sequencia) >= 5
    for c in casos:
        assert c.dados.get("fonte") or c.dados.get("responde") is False, (
            f"{c.id}: caso sem `fonte` e sem `responde: false` não afirma nada")


def test_relatorio_registra_com_quais_modelos_foi_medido(tmp_path, monkeypatch):
    """Antes saía `"modelo": "padrão"` — sem papel, sem provedor, sem o que o painel escolheu."""
    from sdr_shared.config import get_settings
    import sdr_shared.db as db

    monkeypatch.setattr(db, "escolha_de_modelo", lambda papel, **kw: (None, None))
    monkeypatch.setattr(db, "reserva_do_painel", lambda: None)
    monkeypatch.setenv("SDR_LLM_PROVIDER", "anthropic")
    monkeypatch.setenv("SDR_MODEL_CONVERSA", "claude-sonnet-4-5")
    monkeypatch.setenv("SDR_MODEL_ROTEAMENTO", "claude-haiku-4-5")
    monkeypatch.setenv("SDR_LLM_PROVIDER_FALLBACK", "openai")
    monkeypatch.setenv("SDR_EMBEDDINGS_PROVIDER", "openai")
    monkeypatch.setenv("SDR_EMBEDDINGS_MODEL", "text-embedding-3-small")
    get_settings.cache_clear()
    try:
        cfg = relatorio.modelos_configurados()
    finally:
        get_settings.cache_clear()
    assert cfg["roteamento"] | {"de": None} == {"modelo": "claude-haiku-4-5", "provider": "anthropic",
                                                "origem": "ambiente", "de": None}
    assert cfg["analise"]["modelo"] == "claude-sonnet-4-5"
    assert cfg["extracao"]["modelo"] == "claude-haiku-4-5", "extração vazia herda do roteamento"
    assert cfg["informacoes"]["modelo"] == "claude-sonnet-4-5", "informações vazia herda da conversa"
    assert cfg["reserva"] == "openai"
    assert cfg["embeddings"] == {"provider": "openai", "modelo": "text-embedding-3-small"}

    monkeypatch.setattr(db, "escolha_de_modelo",
                        lambda papel, **kw: ("gpt-5.6-luna", "openai") if papel == "roteamento" else (None, None))
    get_settings.cache_clear()
    try:
        cfg = relatorio.modelos_configurados()
    finally:
        get_settings.cache_clear()
    assert cfg["roteamento"]["modelo"] == "gpt-5.6-luna" and cfg["roteamento"]["origem"] == "painel"
    assert cfg["extracao"]["modelo"] == "gpt-5.6-luna", "a troca no painel alcança quem herda"

    monkeypatch.setattr(relatorio, "DIR_RESULTADOS", tmp_path)
    caminho = relatorio.salvar([], {}, {"configurado": cfg, "usado": []})
    assert json.loads(caminho.read_text(encoding="utf-8"))["modelo"]["configurado"]["reserva"] == "openai"


# ------------------------------------------------------------ informações, análise e matriz (ADR-0016)

def test_datasets_de_informacoes_e_analise():
    from evals.suites import _trechos_da_fonte
    casos = carregar("informacoes")
    assert len({c.id for c in casos}) == len(casos)
    assert any(c.get("sem_base") for c in casos) and any(c.get("fonte") for c in casos)
    for c in casos:
        assert c.get("pergunta"), f"{c.id} sem pergunta"
        if not c.get("sem_base"):
            # Renomear o cabeçalho em data/documentos/ não pode quebrar a suíte em silêncio.
            assert _trechos_da_fonte(c["fonte"]), f"{c.id}: seção {c['fonte']!r} não existe"
    from sdr_shared.models import CartaoQualificacao
    for c in carregar("analise"):
        assert len(c["turnos"]) >= 3, f"{c.id}: conversa curta demais para analisar"
        assert all(t.get("mensagem") for t in c["turnos"])
        CartaoQualificacao(**c.get("cartao", {}))


class _Diz:
    def __init__(self, texto):
        self.texto = texto

    def invoke(self, _):
        return type("R", (), {"content": self.texto})()


def test_informacoes_confere_fonte_e_numero_inventado(monkeypatch):
    import agent.llm as llm
    from evals.casos import Caso
    from evals.suites import informacoes
    caso = Caso(id="t", dados={"pergunta": "quanto vocês ficam do aluguel por mês?",
                               "fonte": "Qual a taxa de administração da locação?"})
    monkeypatch.setattr(llm, "llm_informacoes",
                        lambda: _Diz("Depende do contrato. (fonte: Qual a taxa de administração da locação?)"))
    assert informacoes(caso).passou
    monkeypatch.setattr(llm, "llm_informacoes", lambda: _Diz("Cobramos 37% ao mês."))
    r = informacoes(caso)
    assert not r.passou and r.extras["inventou"] and not r.extras["cita_fonte"]
    assert "37" in r.detalhe


def test_informacoes_sem_base_exige_confirmar_e_nenhum_valor(monkeypatch):
    import agent.llm as llm
    from evals.casos import Caso
    from evals.suites import informacoes
    caso = Caso(id="t", dados={"pergunta": "o Brooklin é seguro?", "sem_base": True})
    monkeypatch.setattr(llm, "llm_informacoes", lambda: _Diz("Não tenho essa informação; vou confirmar com um corretor."))
    assert informacoes(caso).passou
    monkeypatch.setattr(llm, "llm_informacoes", lambda: _Diz("Vou confirmar, mas costuma ficar em R$ 800."))
    assert not informacoes(caso).passou


def test_matriz_so_aceita_suite_do_papel_e_isola_o_candidato(monkeypatch):
    import pytest as _pytest
    from evals import matriz
    with _pytest.raises(SystemExit, match="não mede o papel"):
        matriz._candidatos({"conversa": {"suites": ["extracao"], "modelos": ["x/y"]}}, None)
    [(papel, alvo, _suites)] = matriz._candidatos(
        {"_leia": "…", "extracao": {"suites": ["extracao"], "modelos": ["openai/gpt-6-luna"]}}, None)
    assert alvo["provider"] == "openrouter"
    env = matriz._ambiente(papel, alvo)
    assert env["SDR_MODEL_EXTRACAO"] == "openai/gpt-6-luna" and env["SDR_LLM_PROVIDER"] == "openrouter"
    assert env["SDR_LLM_PROVIDER_FALLBACK"] == "", "sem reserva: falha do candidato tem de aparecer"


def test_matriz_resume_metricas_e_falhas_tecnicas():
    from evals import matriz
    m = matriz._metricas({"custo": {"custo_usd": 0.01, "latencia_media_ms": 900, "chamadas": 12}, "suites": [
        {"suite": "extracao", "taxa_aprovacao": 88.0, "acerto_por_campo": 95.0, "alucinacoes": 1,
         "detalhes": [{"detalhe": "exceção: NotFoundError no endpoints found"}, {"detalhe": ""}]}]})
    assert m["extracao: acerto por campo"] == "95.0%" and m["falhas técnicas"] == 1
    assert "| openai/gpt-6-luna |" in matriz._tabela("extracao", [("openai/gpt-6-luna", m)])


def test_todo_papel_tem_suite_na_matriz():
    import json
    from evals import matriz
    from evals.suites import PAPEL_DA_SUITE, SUITES
    from sdr_shared.papeis import PAPEIS
    assert set(PAPEL_DA_SUITE) <= set(SUITES)
    assert set(PAPEL_DA_SUITE.values()) == set(PAPEIS), "papel sem suíte não tem como ser comparado"
    cfg = json.loads(matriz.ARQUIVO.read_text(encoding="utf-8"))
    assert {k for k in cfg if not k.startswith("_")} == set(PAPEIS)
    matriz._candidatos(cfg, None)                       # valida suíte × papel do arquivo real


def test_matriz_recusa_rodar_sem_a_chave_do_provedor(monkeypatch):
    """Sem a chave, cada candidato leva 401 em toda chamada e a tabela sai com números iguais para
    todos — que parecem resultado. Aconteceu na primeira execução real."""
    from evals import matriz
    alvos = matriz._candidatos({"extracao": {"suites": ["extracao"], "modelos": ["openai/gpt-6-luna"]}}, None)
    monkeypatch.delenv("SDR_OPENROUTER_API_KEY", raising=False)
    falta = matriz._falta_credencial(alvos)
    assert "SDR_OPENROUTER_API_KEY" in falta and "--force-recreate" in falta
    monkeypatch.setenv("SDR_OPENROUTER_API_KEY", "sk-or-teste")
    assert matriz._falta_credencial(alvos) is None


def test_matriz_denuncia_erro_e_modelo_trocado():
    """Na primeira matriz real, o gpt-oss-120b falhou em todas as chamadas sem nenhuma falha técnica
    na tabela (a extração engole a exceção), e 23 chamadas do Sonnet 5 foram atendidas pelo Haiku."""
    from evals import matriz
    r = {"custo": {"custo_usd": 0.0, "latencia_media_ms": 0, "chamadas": 132, "chamadas_com_erro": 132,
                   "erro_exemplo": "BadRequestError: reasoning effort 'none' not supported"},
         "modelo": {"usado": [{"modelo": "anthropic/claude-sonnet-5", "chamadas": 109},
                              {"modelo": "anthropic/claude-haiku-4.5", "chamadas": 23}]},
         "suites": []}
    m = matriz._metricas(r, "anthropic/claude-sonnet-5")
    assert m["chamadas com erro"] == 132 and m["atendidas por outro modelo"] == 23
    tabela = matriz._tabela("extracao", [("anthropic/claude-sonnet-5", m)])
    assert "_erro" not in tabela.split("\n")[2], "o erro vai para o rodapé, não vira coluna"
    assert "reasoning effort 'none'" in tabela


def test_eval_ignora_o_orcamento(monkeypatch):
    import agent.llm as llm
    import sdr_shared.ports as ports
    import sdr_shared.ports.factory as factory
    from evals.__main__ import _ignorar_orcamento
    # Os três pelo monkeypatch, para ele os restaurar depois: `_ignorar_orcamento` troca o atributo
    # direto, e sem isso o "normal" vazaria para os testes seguintes da sessão.
    for mod in (factory, ports, llm):
        monkeypatch.setattr(mod, "modo_do_agente", lambda: "degradado")
    _ignorar_orcamento()
    assert factory.modo_do_agente() == "normal" and llm.modo_do_agente() == "normal"


def test_numero_por_extenso_no_trecho_nao_conta_como_inventado():
    """A primeira matriz de `informacoes`: todo candidato "inventou" 10, 6 e 30 — que o documento
    escreve como "Dez por cento", "Seis por cento" e "trinta dias". Converter não é inventar."""
    from evals.suites import _por_extenso

    assert _por_extenso("Dez por cento do valor do aluguel") == {"10"}
    assert "30" in _por_extenso("comunicado com trinta dias de antecedência")
    assert "25" in _por_extenso("vinte e cinco dias")
    assert "2500" in _por_extenso("dois mil e quinhentos reais")
    assert "100" not in _por_extenso("seis por cento"), "'por cento' não é o número cem"
