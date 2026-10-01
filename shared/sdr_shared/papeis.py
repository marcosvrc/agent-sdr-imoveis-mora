"""Papéis de modelo: QUAL função do agente uma chamada de LLM serve (ADR-0010, ADR-0016).

Um papel existe quando a função pede um modelo diferente — não quando existe um nó a mais. Eram três
(conversa, roteamento, analise) e dois deles juntavam funções com exigências opostas:

- `roteamento` servia o supervisor (uma palavra, em toda mensagem ambígua) E a extração do cartão
  (JSON estruturado, em todo turno de qualificação). O primeiro quer o modelo mais rápido que exista;
  o segundo quer o que menos erra em saída estruturada — e esses raramente são o mesmo modelo.
- `conversa` servia a fala da Mora E a resposta do RAG institucional, que precisa ficar presa ao
  trecho recuperado e citar a fonte. Persona e fidelidade não se otimizam juntas.

Daí `extracao` e `informacoes`. Os dois HERDAM do papel de onde saíram: com o campo vazio no painel e
sem variável própria no ambiente, o comportamento é exatamente o de antes da divisão.

Este módulo é a fonte única. API, factory, harness de avaliação, comparação e painel leem daqui —
a lista escrita à mão em cinco lugares é o que fazia um papel novo existir em um e faltar em outro.
"""

PAPEIS: tuple[str, ...] = ("conversa", "roteamento", "extracao", "informacoes", "analise")

# Papel vazio herda deste. Encadeia: `analise` → `conversa`; `extracao` → `roteamento`.
HERDA: dict[str, str] = {"extracao": "roteamento", "informacoes": "conversa", "analise": "conversa"}

# O que é cada papel, em uma linha — a tela mostra isto ao lado do campo.
DESCRICAO: dict[str, str] = {
    "conversa": "Fala com o cliente: qualificador, consultor, agendador, follow-up, reativação.",
    "roteamento": "Decide o próximo nó quando a regra não decide. Uma palavra; roda muito.",
    "extracao": "Preenche o cartão do lead em JSON estruturado, em todo turno de qualificação.",
    "informacoes": "Responde política da imobiliária a partir dos documentos, citando a fonte.",
    "analise": "Briefing e análise do lead para o corretor. Fora do turno: latência não importa.",
}

# Classificar e extrair querem a resposta mais provável, não a mais variada. A conversa quer um pouco
# de variação para não soar como formulário. `informacoes` fica com a da conversa de propósito: baixar
# é um ajuste a MEDIR (o harness ainda não tem suíte de fidelidade da resposta), não a supor.
TEMPERATURA: dict[str, float] = {"conversa": 0.6, "roteamento": 0.0, "extracao": 0.0,
                                 "informacoes": 0.6, "analise": 0.6}

# Teto de saída. 600 cabe folgado numa fala de mensageiro e na decisão do roteador, mas não na análise
# do resumidor: `AnaliseLead` tem onze campos, quatro deles listas de 3 a 5 itens, e sai como JSON.
# Truncada, a saída estruturada não valida, o `except` do resumidor engole e o corretor fica sem a
# análise — sem nada no painel dizendo que ela faltou.
MAX_TOKENS: dict[str, int] = {"conversa": 600, "roteamento": 600, "extracao": 600,
                              "informacoes": 600, "analise": 1500}

# Esforço de raciocínio para os modelos que raciocinam por padrão (Claude 5.x, GPT-5/6, Gemini 3.x).
# Nenhum papel do turno ganha com o modelo pensando antes de falar: o cliente espera, e o que decide a
# qualidade aqui é o prompt e o dado recuperado. A análise roda fora do turno e pode pensar mais.
# `none` não existe em todo provedor; o factory traduz para o mínimo que cada um aceita.
ESFORCO: dict[str, str] = {"conversa": "low", "roteamento": "none", "extracao": "none",
                           "informacoes": "low", "analise": "medium"}

# Critério de escolha do provedor no OpenRouter (campo `provider.sort`). O mesmo modelo é servido por
# vários provedores com velocidades diferentes; o papel diz qual número importa.
# - roteamento/extração: saída curta, então o que o cliente sente é o tempo até o primeiro token.
# - conversa/informações: 150–300 tokens de saída, então pesa a velocidade de geração.
# - análise: ninguém está esperando.
ORDENACAO_OPENROUTER: dict[str, str] = {"conversa": "throughput", "roteamento": "latency",
                                        "extracao": "latency", "informacoes": "throughput",
                                        "analise": "price"}

# Papel que ATENDE quando o orçamento estoura e o agente degrada: o barato. Todos os outros caem nele
# — inclusive `extracao`, que se alguém apontar para um modelo caro não pode furar a degradação.
BARATO = "roteamento"


def pai(papel: str) -> str | None:
    return HERDA.get(papel)


def cadeia(papel: str) -> list[str]:
    """O papel e seus ancestrais, na ordem de consulta: `analise` → [analise, conversa]."""
    saida, atual = [], papel
    while atual and atual not in saida:
        saida.append(atual)
        atual = HERDA.get(atual)
    return saida


def raiz(papel: str) -> str:
    """O papel de base (conversa ou roteamento) — o que decide o modelo padrão do ambiente."""
    return cadeia(papel)[-1]


def valido(papel: str) -> bool:
    return papel in PAPEIS
