"""O harness também pode quebrar — dataset malformado, campo renomeado, métrica com divisão por zero.

Estes testes rodam o harness em modo falso (sem chamar API) só para garantir que ele EXECUTA e
produz números coerentes. Não afirmam nada sobre a qualidade do modelo: isso é o `make eval`.
"""
import json

import pytest

from evals import relatorio
from evals.casos import Resultado, carregar, combina, vazio


@pytest.mark.parametrize("nome", ["extracao", "roteamento", "adversarial"])
def test_dataset_carrega_e_tem_o_formato_esperado(nome):
    casos = carregar(nome)
    assert casos, f"dataset {nome} vazio"
    assert len({c.id for c in casos}) == len(casos), "ids repetidos no dataset"
    for c in casos:
        assert "mensagem" in c.dados, f"{c.id} sem mensagem"
        if nome == "extracao":
            assert "esperado" in c.dados and "nao_esperado" in c.dados, (
                f"{c.id}: sempre declare nao_esperado — é ele que mede alucinação")
        if nome == "roteamento":
            assert c["esperado"] in ("qualificador", "consultor", "agendador",
                                     "followup", "handoff", "recusa", "resumidor")
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
