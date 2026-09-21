"""Cascata da busca de imóveis (docs/architecture/dados.md)."""
from base import Diagrama, gerar


def montar() -> Diagrama:
    d = Diagrama(
        nome="busca-cascata", titulo="Cascata da busca de imóveis",
        subtitulo="Do bairro pedido até a cidade, dizendo sempre até onde precisou ir",
        largura=1960, altura=820,
        alt=("A busca tenta o bairro pedido, depois os vizinhos, a região e a cidade; o nível "
             "alcançado vai para o prompt e o agente não afirma indisponibilidade fora dele."))

    d.cartao(46, 236, 250, 110, "Cartão do lead", ["Intenção, bairros, preço,", "quartos, urgência"], "lista", "azul")
    d.cartao(46, 400, 250, 96, "Um embedding", ["por busca, não por nível"], "caixas", "roxo")

    passos = [
        ("Bairro pedido", "o que o cliente falou", "alvo"),
        ("Bairros vizinhos", "mesma região, mais próximos", "lupa"),
        ("Região", "zona sul, oeste…", "lupa"),
        ("Cidade", "melhor algo bom fora da área\nque dizer que não há nada", "predio"),
    ]
    x0, larg, gap = 380, 310, 90
    for i, (t, sub, ic) in enumerate(passos):
        x = x0 + i * (larg + gap)
        linhas = sub.split("\n")
        d.cartao(x, 236, larg, 110, t, linhas, ic, "azul", pequeno=True)
        d.add(f'<text x="{x + larg / 2}" y="{206}" class="t-mini" text-anchor="middle">'
              f'nível "{["bairro", "vizinhos", "regiao", "cidade"][i]}"</text>')
        if i < 3:
            d.aresta([(x + larg, 291), (x + larg + gap, 291)], "azul",
                     rot_xy=(x + larg + gap / 2, 266), rot_linhas=["sem resultado"])
        d.aresta([(x + larg / 2, 346), (x + larg / 2, 430)], "cinza", ponta=False)

    d.cartao(380, 430, 1510, 96, "Filtros SQL + similaridade de cosseno, na mesma consulta",
             ["operação · região · bairros · preço (+15 %) · quartos mínimos — ImovelRepository.buscar_hibrido"],
             "banco", "cinza", pequeno=True)
    d.cartao(380, 588, 740, 110, "Imóveis recomendados", ["Até 3 por turno, sem repetir o que já foi visto", "ou descartado (tabela interesses)"], "certo", "verde", pequeno=True)
    d.cartao(1150, 588, 740, 110, "Alternativa no bairro pedido", ["Relaxa quartos e depois preço: “de 2 quartos não", "tenho aí, mas tenho este de 1”"], "mao", "verde", pequeno=True)

    d.aresta([(296, 291), (380, 291)], "azul")
    d.aresta([(296, 448), (340, 448), (340, 478), (380, 478)], "roxo", raio=10)
    d.aresta([(750, 526), (750, 588)], "verde")
    d.aresta([(1520, 526), (1520, 588)], "verde")

    d.nota(980, 720, 1300, [
        "Sem embedder no ar (Ollama fora, provedor sem chave) a busca cai para os filtros SQL puros e devolve sem_embedding — "
        "pior que a semântica, melhor que derrubar o turno."])
    d.legenda([("azul", "Descida da cascata"), ("roxo", "Vetor"), ("verde", "Saída para o cliente"),
               ("cinza", "Consulta ao índice")], y=800)
    return d


if __name__ == "__main__":
    print("\n".join(gerar(montar())))
