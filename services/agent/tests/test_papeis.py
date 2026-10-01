"""Cada papel tem acessor, e cada nó chama o acessor do papel certo (ADR-0016)."""
import inspect

from sdr_shared.papeis import PAPEIS


def test_todo_papel_tem_acessor_e_a_lista_do_duble_esta_completa():
    """`ACESSORES` é o que o dublê dos testes e o modo falso do harness trocam. Um acessor fora
    dela chamaria o modelo de verdade no meio da suíte — e a conta apareceria na fatura."""
    import agent.llm as llm
    assert set(llm.ACESSORES) == {f"llm_{p}" for p in PAPEIS}
    assert {n for n in dir(llm) if n.startswith("llm_")} == set(llm.ACESSORES)


def test_extracao_e_informacoes_usam_o_papel_proprio():
    """Antes a extração usava `llm_roteamento` e o RAG usava `llm_conversa`: trocar o modelo do
    supervisor trocava, sem ninguém pedir, o que preenche o cartão do lead."""
    from agent.nodes import informacoes, qualificador, supervisor
    assert "llm_extracao()" in inspect.getsource(qualificador._extrair)
    assert "llm_roteamento" not in inspect.getsource(qualificador)
    assert "llm_informacoes()" in inspect.getsource(informacoes.run)
    assert "llm_roteamento()" in inspect.getsource(supervisor.run)
