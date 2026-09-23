"""Gera data/imoveis/imoveis.json com imóveis sintéticos variados (determinístico: mesma seed, mesma base).

Uso: python scripts/gerar_imoveis.py [residenciais=250] [comerciais=150] [seed=42]

Ordem do arquivo, e por que ela importa: primeiro os CURADOS (a fixture dos testes do agente, que
aparecem no roteiro da demo), depois os residenciais gerados e, no FIM, os comerciais. Acrescentar
no fim mantém os índices dos anteriores, e há seed e teste que dependem da posição — a descrição
com injeção de prompt mora no índice 7 e o imóvel indisponível no 11 (services/crm/.../seed/gerar.py).

Os ids gerados começam em 100 (SP-0100, CJ-0100) para não colidirem com os curados, que ficam na
faixa baixa. Colisão aqui não daria erro: daria dois imóveis com o mesmo código, e o `code` é a
chave entre a Mora e o CRM.

Preços são plausíveis, não reais: o fator por bairro abaixo é uma escala relativa inventada para o
acervo de demonstração ter faixas distintas (um lead com orçamento de R$ 400 mil precisa encontrar
bairro onde isso compre algo). Não é pesquisa de mercado e não deve ser lido como tal.
"""
import json
import random
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]

REGIOES = {
    "zona_sul": ["Brooklin", "Moema", "Campo Belo", "Vila Mariana", "Itaim Bibi"],
    "zona_oeste": ["Pinheiros", "Perdizes", "Lapa", "Butantã"],
    "zona_norte": ["Santana", "Tucuruvi", "Casa Verde"],
    "zona_leste": ["Tatuapé", "Mooca", "Anália Franco"],
    "centro": ["República", "Bela Vista", "Consolação"],
}
# Escala relativa fictícia (ver o cabeçalho): 1,0 é a média do acervo.
FATOR_BAIRRO = {
    "Itaim Bibi": 1.45, "Moema": 1.35, "Pinheiros": 1.30, "Brooklin": 1.15, "Campo Belo": 1.15,
    "Vila Mariana": 1.10, "Perdizes": 1.10, "Anália Franco": 1.00, "Consolação": 1.00,
    "Santana": 0.92, "Tatuapé": 0.92, "Lapa": 0.90, "Mooca": 0.90, "Bela Vista": 0.88,
    "Butantã": 0.88, "Casa Verde": 0.80, "Tucuruvi": 0.78, "República": 0.78,
}

# Peso por tipo: o acervo imita uma carteira de imobiliária de bairro, onde apartamento domina.
TIPOS_RESIDENCIAIS = (
    ["apartamento"] * 10 + ["casa"] * 3 + ["studio"] * 3 + ["sobrado"] * 2 + ["cobertura"] + ["kitnet"]
)
TIPOS_COMERCIAIS = (
    ["sala comercial"] * 6 + ["conjunto comercial"] * 3 + ["loja"] * 3 + ["galpão"] * 2
    + ["laje corporativa"]
)

DESCRICOES = {
    "apartamento": [
        "Andar alto com vista livre e sol da manhã.",
        "Reformado, pronto para morar, armários planejados.",
        "A poucos minutos do metrô, cercado de comércio e serviços.",
        "Condomínio com lazer completo: piscina, academia e salão de festas.",
        "Planta inteligente, sala ampla integrada à varanda.",
        "Prédio novo com coworking, lavanderia e bicicletário.",
    ],
    "casa": [
        "Rua tranquila e arborizada, ótima para quem tem crianças.",
        "Quintal com churrasqueira e espaço para horta.",
        "Casa térrea em vila fechada, sem escadas.",
    ],
    "sobrado": [
        "Sobrado com suíte no andar de cima e lavabo social embaixo.",
        "Dois pavimentos, garagem coberta para dois carros.",
        "Sobrado reformado em rua sem saída, silencioso.",
    ],
    "studio": [
        "Studio compacto e bem resolvido, mobiliado.",
        "Prédio com portaria 24h e academia, a uma quadra do metrô.",
        "Ideal para quem mora só e trabalha na região.",
    ],
    "kitnet": [
        "Kitnet reformada, contas de consumo inclusas no condomínio.",
        "Próxima à faculdade e ao comércio de rua.",
    ],
    "cobertura": [
        "Cobertura duplex com terraço, churrasqueira e vista aberta.",
        "Último andar com terraço privativo e vista para o parque.",
    ],
    "sala comercial": [
        "Sala em prédio comercial com recepção e elevador social.",
        "Sala pronta para ocupar, com ar-condicionado instalado.",
        "Andar corporativo com copa compartilhada e bicicletário.",
    ],
    "conjunto comercial": [
        "Conjunto com copa, dois banheiros e divisórias removíveis.",
        "Pé-direito alto, pronto para layout aberto.",
        "Dois conjuntos integrados, com sala de reunião fechada.",
    ],
    "loja": [
        "Piso térreo com vitrine para a rua, ótimo fluxo de pedestres.",
        "Loja de esquina com dois acessos e depósito nos fundos.",
        "Ponto consolidado em rua de comércio, com mezanino.",
    ],
    "galpão": [
        "Galpão com doca e acesso para carga e descarga.",
        "Pé-direito de 8 metros, piso de alta resistência.",
        "Galpão com escritório interno e pátio de manobra.",
    ],
    "laje corporativa": [
        "Laje corporativa com ar-condicionado central e cabeamento estruturado.",
        "Andar inteiro com piso elevado e gerador.",
    ],
}

# --- fotos -------------------------------------------------------------------------------------
# O pool é um arquivo de dados, e não uma lista aqui dentro: trocar as fotos pelas reais (baixadas
# para data/fotos-acervo/) é rodar `python scripts/indexar_fotos.py` e regerar — sem tocar neste
# script. Pool vazio cai em URL de serviço de exemplo, para a galeria já ter mais de uma foto.
POOL_ARQ = RAIZ / "data/imoveis/fotos_pool.json"
POOL: dict[str, list[str]] = {}
if POOL_ARQ.is_file():
    POOL = {k: v for k, v in json.loads(POOL_ARQ.read_text(encoding="utf-8")).items()
            if not k.startswith("_") and isinstance(v, list)}

CATEGORIA_DA_FOTO = {
    "sala comercial": "sala-comercial", "conjunto comercial": "sala-comercial",
    "laje corporativa": "sala-comercial", "loja": "loja", "galpão": "galpao",
}


def _fotos(tipo: str, chave: str, rnd: random.Random) -> list[str]:
    """Duas ou três fotos por imóvel, coerentes com o tipo (galpão não recebe foto de sala de estar).

    A capa é `fotos[0]` em toda a vitrine, então a ordem é escolhida aqui, e não no front.
    """
    categoria = CATEGORIA_DA_FOTO.get(tipo, "residencial")
    quantas = rnd.randint(2, 3)
    disponiveis = POOL.get(categoria) or []
    if len(disponiveis) >= 2:
        return rnd.sample(disponiveis, min(quantas, len(disponiveis)))
    return [f"https://picsum.photos/seed/{chave}-{n}/1200/800" for n in range(1, quantas + 1)]


def _preco(area: float, por_m2: tuple[float, float], bairro: str, rnd: random.Random,
           venda: bool) -> float:
    valor = area * rnd.uniform(*por_m2) * FATOR_BAIRRO.get(bairro, 1.0)
    return float(round(valor, -3 if venda else -1))


def gerar(i: int, rnd: random.Random) -> dict:
    regiao = rnd.choice(list(REGIOES))
    bairro = rnd.choice(REGIOES[regiao])
    tipo = rnd.choice(TIPOS_RESIDENCIAIS)
    operacao = rnd.choice(["venda", "venda", "aluguel"])
    if tipo in ("studio", "kitnet"):
        quartos, area = 1, float(round(rnd.uniform(20, 45)))
    elif tipo == "cobertura":
        quartos, area = rnd.randint(3, 4), float(round(rnd.uniform(140, 320)))
    elif tipo in ("casa", "sobrado"):
        quartos, area = rnd.randint(2, 4), float(round(rnd.uniform(90, 260)))
    else:
        quartos = rnd.randint(1, 4)
        area = float(round(rnd.uniform(28, 55) * quartos + rnd.uniform(0, 25)))
    # Cobertura e kitnet puxam o preço por metro para lados opostos; o resto fica na faixa média.
    faixa_venda = {"cobertura": (14_000, 22_000), "kitnet": (6_000, 9_000),
                   "studio": (9_000, 14_000)}.get(tipo, (9_000, 16_000))
    faixa_aluguel = {"cobertura": (70, 120), "kitnet": (30, 55)}.get(tipo, (45, 95))
    venda = operacao == "venda"
    return {
        "id": f"SP-{i:04d}", "tipo": tipo, "operacao": operacao, "cidade": "São Paulo",
        "regiao": regiao, "bairro": bairro, "quartos": quartos,
        "suites": 0 if quartos == 1 else rnd.randint(1, min(quartos - 1, 2)),
        "vagas": 0 if tipo == "kitnet" else rnd.randint(0, 3 if tipo == "cobertura" else 2),
        "area_m2": area,
        "preco": _preco(area, faixa_venda if venda else faixa_aluguel, bairro, rnd, venda),
        # Casa e sobrado não têm condomínio; ausente é DESCONHECIDO, e o CRM o trata como tal.
        "condominio": (None if tipo in ("casa", "sobrado") else
                       float(round(area * rnd.uniform(9, 16) * FATOR_BAIRRO.get(bairro, 1.0), -1))),
        "descricao": rnd.choice(DESCRICOES[tipo]),
        "fotos": _fotos(tipo, f"sp{i:04d}", rnd),
        "destaque_investimento": rnd.random() < 0.3,
    }


# Comercial não é residencial sem quartos: o que caracteriza é a área e o uso. Por isso `quartos`
# fica em 0 (é o número de dormitórios, e não existe), a área tem outra faixa e o preço por m² é
# outro — sala custa mais por metro que apartamento, galpão custa bem menos.
def gerar_comercial(i: int, rnd: random.Random) -> dict:
    regiao = rnd.choice(list(REGIOES))
    bairro = rnd.choice(REGIOES[regiao])
    tipo = rnd.choice(TIPOS_COMERCIAIS)
    operacao = rnd.choice(["aluguel", "aluguel", "venda"])   # comercial se aluga mais do que se compra
    area = float(round({
        "galpão": rnd.uniform(180, 900),
        "laje corporativa": rnd.uniform(220, 700),
        "loja": rnd.uniform(35, 220),
    }.get(tipo, rnd.uniform(28, 180))))
    faixa_aluguel = {"galpão": (22, 38), "loja": (70, 130),
                     "laje corporativa": (90, 160)}.get(tipo, (55, 105))
    faixa_venda = {"galpão": (4_000, 7_000),
                   "laje corporativa": (12_000, 20_000)}.get(tipo, (8_000, 15_000))
    venda = operacao == "venda"
    return {
        "id": f"CJ-{i:04d}", "tipo": tipo, "operacao": operacao, "cidade": "São Paulo",
        "regiao": regiao, "bairro": bairro,
        "quartos": 0, "suites": 0,                     # dormitório não é atributo de sala nem de loja
        "vagas": rnd.randint(0, 6 if tipo == "laje corporativa" else 4),
        "area_m2": area,
        "preco": _preco(area, faixa_venda if venda else faixa_aluguel, bairro, rnd, venda),
        "condominio": (None if tipo == "galpão" else
                       float(round(area * rnd.uniform(14, 28) * FATOR_BAIRRO.get(bairro, 1.0), -1))),
        "descricao": rnd.choice(DESCRICOES[tipo]),
        "fotos": _fotos(tipo, f"cj{i:04d}", rnd),
        "destaque_investimento": rnd.random() < 0.45,   # comercial aparece mais como investimento
    }


CURADOS = json.loads((RAIZ / "services/agent/tests/fixtures/imoveis.json").read_text(encoding="utf-8"))
SO_COMERCIAIS = set(CATEGORIA_DA_FOTO)


def main(residenciais: int = 250, comerciais: int = 150, seed: int = 42) -> None:
    rnd = random.Random(seed)
    curados_res = [x for x in CURADOS if x["tipo"] not in SO_COMERCIAIS]
    curados_com = [x for x in CURADOS if x["tipo"] in SO_COMERCIAIS]
    imoveis = curados_res + curados_com
    imoveis += [gerar(i, rnd) for i in range(100, 100 + max(0, residenciais - len(curados_res)))]
    imoveis += [gerar_comercial(i, rnd)
                for i in range(100, 100 + max(0, comerciais - len(curados_com)))]
    vistos: set[str] = set()
    repetidos = sorted({x["id"] for x in imoveis if x["id"] in vistos or vistos.add(x["id"])})
    if repetidos:      # `code` é a chave entre a Mora e o CRM: duas linhas com o mesmo código é
        raise SystemExit(f"✗ ids repetidos: {repetidos}")            # corrupção silenciosa, não erro
    destino = RAIZ / "data/imoveis/imoveis.json"
    destino.write_text(json.dumps(imoveis, ensure_ascii=False, indent=2), encoding="utf-8")
    fonte = (f"pool de {sum(len(v) for v in POOL.values())} fotos"
             if POOL else "fotos de exemplo (pool vazio)")
    print(f"{len(imoveis)} imóveis — {residenciais} residenciais, {comerciais} comerciais; "
          f"{fonte} — em {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:4]))
