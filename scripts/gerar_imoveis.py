"""Gera data/imoveis/imoveis.json com N imóveis sintéticos variados (determinístico: mesma seed, mesma base).

Uso: python scripts/gerar_imoveis.py [N=200] [seed=42]
Os 3 primeiros são curados (usados nos exemplos e no roteiro da demo); depois vêm os residenciais
gerados e, no FIM, os comerciais — acrescentar no fim mantém os índices dos anteriores, e há teste
e seed que dependem da posição (a descrição com injeção, por exemplo, mora no índice 7).
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
DESCRICOES_COMERCIAIS = [
    "Sala em prédio comercial com recepção e elevador social.",
    "Piso térreo com vitrine para a rua, ótimo fluxo de pedestres.",
    "Pé-direito alto, pronto para layout aberto.",
    "Laje corporativa com ar-condicionado central e cabeamento estruturado.",
    "Galpão com doca e acesso para carga e descarga.",
    "Conjunto com copa, dois banheiros e divisórias removíveis.",
]
DESCRICOES = [
    "Andar alto com vista livre e sol da manhã.",
    "Reformado, pronto para morar, armários planejados.",
    "A poucos minutos do metrô, cercado de comércio e serviços.",
    "Condomínio com lazer completo: piscina, academia e salão de festas.",
    "Rua tranquila e arborizada, ótima para quem tem crianças.",
    "Planta inteligente, sala ampla integrada à varanda.",
    "Prédio novo com coworking, lavanderia e bicicletário.",
]
CURADOS = json.loads((RAIZ / "services/agent/tests/fixtures/imoveis.json").read_text(encoding="utf-8"))


def gerar(i: int, rnd: random.Random) -> dict:
    regiao = rnd.choice(list(REGIOES))
    tipo = rnd.choice(["apartamento", "apartamento", "apartamento", "casa", "studio"])
    operacao = rnd.choice(["venda", "venda", "aluguel"])
    quartos = 1 if tipo == "studio" else rnd.randint(1, 4)
    area = float(round(rnd.uniform(28, 55) * max(quartos, 1) + rnd.uniform(0, 25)))
    if operacao == "venda":
        preco = float(round(area * rnd.uniform(9_000, 16_000), -3))
    else:
        preco = float(round(area * rnd.uniform(45, 95), -1))
    return {
        "id": f"SP-{i:04d}", "tipo": tipo, "operacao": operacao, "cidade": "São Paulo", "regiao": regiao,
        "bairro": rnd.choice(REGIOES[regiao]), "quartos": quartos,
        "suites": 0 if quartos == 1 else rnd.randint(1, min(quartos - 1, 2)),
        "vagas": rnd.randint(0, 2), "area_m2": area, "preco": preco,
        "condominio": float(round(area * rnd.uniform(9, 16), -1)) if tipo != "casa" else None,
        "descricao": rnd.choice(DESCRICOES),
        "fotos": [f"https://picsum.photos/seed/sp{i:04d}/800/600"],
        "destaque_investimento": rnd.random() < 0.3,
    }


# Comercial não é residencial sem quartos: o que caracteriza é a área e o uso. Por isso `quartos`
# fica em 0 (é o número de dormitórios, e não existe), a área tem outra faixa e o preço por m² é
# outro — sala custa mais por metro que apartamento, galpão custa bem menos.
TIPOS_COMERCIAIS = ["sala comercial", "sala comercial", "loja", "conjunto comercial", "galpão"]


def gerar_comercial(i: int, rnd: random.Random) -> dict:
    regiao = rnd.choice(list(REGIOES))
    tipo = rnd.choice(TIPOS_COMERCIAIS)
    operacao = rnd.choice(["aluguel", "aluguel", "venda"])   # comercial se aluga mais do que se compra
    area = float(round(rnd.uniform(180, 600) if tipo == "galpão" else rnd.uniform(28, 180)))
    por_m2 = {"galpão": (22, 38), "loja": (70, 130)}.get(tipo, (55, 105))
    if operacao == "venda":
        preco = float(round(area * rnd.uniform(6_000, 14_000), -3))
    else:
        preco = float(round(area * rnd.uniform(*por_m2), -1))
    return {
        "id": f"CJ-{i:04d}", "tipo": tipo, "operacao": operacao, "cidade": "São Paulo", "regiao": regiao,
        "bairro": rnd.choice(REGIOES[regiao]),
        "quartos": 0, "suites": 0,                     # dormitório não é atributo de sala nem de loja
        "vagas": rnd.randint(0, 4), "area_m2": area, "preco": preco,
        "condominio": float(round(area * rnd.uniform(14, 28), -1)) if tipo != "galpão" else None,
        "descricao": rnd.choice(DESCRICOES_COMERCIAIS),
        "fotos": [f"https://picsum.photos/seed/cj{i:04d}/800/600"],
        "destaque_investimento": rnd.random() < 0.45,   # comercial aparece mais como investimento
    }


def main(n: int = 200, seed: int = 42, comerciais: int = 40) -> None:
    rnd = random.Random(seed)
    imoveis = CURADOS + [gerar(i, rnd) for i in range(100, 100 + n - len(CURADOS))]
    imoveis += [gerar_comercial(i, rnd) for i in range(1, comerciais + 1)]
    destino = RAIZ / "data/imoveis/imoveis.json"
    destino.write_text(json.dumps(imoveis, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(imoveis)} imóveis ({comerciais} comerciais) em {destino.relative_to(RAIZ)}")


if __name__ == "__main__":
    main(*(int(a) for a in sys.argv[1:3]))
