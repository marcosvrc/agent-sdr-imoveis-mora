"""Harness de avaliação do agente: mede o MODELO, não o encanamento.

A suíte de `tests/` roda com LLM falso — prova que grafo, persistência e despacho funcionam, é
determinística e cabe no CI. Isto aqui é o oposto: chama o modelo de verdade para responder o que
os testes não conseguem — o qualificador entende português bagunçado? o supervisor roteia certo?
um jailbreak passa? Custa dinheiro e varia entre execuções, então vive fora do portão de commit.
"""
