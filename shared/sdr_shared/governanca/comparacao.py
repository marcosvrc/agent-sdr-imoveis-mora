"""Comparação entre modelos para a tela de configuração.

O que esta comparação mostra é deliberadamente restrito ao que o projeto MEDE ou DECIDE:

- **custo**: sai da tabela de preços — a mesma que o painel usa para recusar modelo sem preço;
- **latência**: mediana das chamadas reais gravadas em `uso_llm`, no ambiente de quem está olhando;
- **papel recomendado**: a tabela `_EQUIVALENTE` do factory, que é decisão documentada do projeto.

Janela de contexto, limite de tokens e "velocidade" como especificação de fornecedor ficaram de
fora porque não existem em lugar nenhum do repositório. Preencher esses campos de memória deixaria
a tela mais bonita e faria alguém escolher um modelo por um número inventado — numa tela cuja
função é justamente decidir qual modelo atende o cliente.
"""
from .precos import custo_usd, preco_do_modelo

# Quando ainda não há uso gravado, é preciso ALGUM mix para ordenar do mais barato ao mais caro:
# um modelo só tem "um preço" depois que se fixa a proporção entrada/saída. 3:1 é a proporção típica
# de conversa curta com histórico. Fica marcado como `base: "referencia"` para a tela poder dizer
# que é estimativa, e não o gasto de ninguém.
MIX_REFERENCIA = {"entrada": 3000, "saida": 1000, "cache_escrita": 0, "cache_leitura": 0, "chamadas": 0}

CAMPOS_PRECO = ("entrada", "saida", "cache_escrita", "cache_leitura")


def recomendacoes(equivalente: dict[str, dict[str, str]]) -> dict[str, str]:
    """`{modelo: papel}` a partir da tabela de equivalência por papel do factory.

    Conversa antes de análise: os dois costumam apontar para o mesmo modelo, e "conversa" é o papel
    que explica a escolha (qualidade para o que o cliente lê)."""
    saida: dict[str, str] = {}
    for papeis in equivalente.values():
        for papel in ("conversa", "roteamento", "analise"):
            if (m := papeis.get(papel)) and m not in saida:
                saida[m] = papel
    return saida


def comparar(*, catalogo: dict[str, list[str]], mix: dict, latencias: dict,
             recomendado: dict[str, str], tabela: dict | None = None, dias: int = 30) -> list[dict]:
    """Uma linha por modelo do catálogo, da mais barata para a mais cara.

    O custo é contrafactual: os tokens que ESTE papel realmente consumiu, reprecificados com a
    tabela de cada modelo. É uma estimativa e não uma previsão — trocar de modelo muda o tamanho da
    resposta, e cache entre provedores não se comporta igual. Mas erra muito menos que comparar
    preço por milhão de tokens no abstrato, que não sabe se o papel gasta mais entrada ou saída.
    """
    usa_uso = bool(mix.get("chamadas"))
    tokens = mix if usa_uso else MIX_REFERENCIA
    linhas = []
    for provedor, modelos in catalogo.items():
        for m in modelos:
            if not (p := preco_do_modelo(m, tabela)):
                continue
            linhas.append({
                "modelo": m,
                "provedor": provedor,
                "preco": dict(zip(CAMPOS_PRECO, p, strict=True)),
                "recomendado_para": recomendado.get(m),
                "latencia": latencias.get(m) or {"mediana_ms": None, "amostras": 0, "escopo": None},
                "custo": {
                    "usd": custo_usd(m, tokens.get("entrada", 0), tokens.get("saida", 0),
                                     tokens.get("cache_escrita", 0), tokens.get("cache_leitura", 0), tabela),
                    "base": "uso" if usa_uso else "referencia",
                    "dias": dias if usa_uso else None,
                    "chamadas": int(mix.get("chamadas") or 0),
                },
            })
    return sorted(linhas, key=lambda l: (l["custo"]["usd"], l["modelo"]))
