"""Resolvedor de localidade: o cliente fala um lugar, o sistema descobre o que isso é.

O cliente nunca diz "zona_oeste". Ele diz "Pinheiros", "pinheiro", "Vila Madalena", "perto da Faria
Lima", "zona sul", "SP" ou "Osasco". Este módulo traduz qualquer uma dessas formas para o que a busca
entende — bairro, região, cidade ou fora de cobertura — sem depender do LLM acertar o mapeamento.

O catálogo é da POC (São Paulo capital, os bairros da base simulada). Para produção, viraria tabela.
"""
import re
import unicodedata
from dataclasses import dataclass, field
from difflib import get_close_matches

CIDADE_PADRAO = "São Paulo"

# bairro canônico -> região, apelidos (como o cliente fala) e pontos de referência
BAIRROS: dict[str, dict] = {
    "Brooklin":      {"regiao": "zona_sul",   "apelidos": ["brooklin novo", "brooklin paulista"], "refs": ["berrini", "chucri zaidan", "morumbi shopping", "ponte estaiada"]},
    "Moema":         {"regiao": "zona_sul",   "apelidos": ["moema índios", "moema pássaros"], "refs": ["ibirapuera", "parque ibirapuera", "shopping ibirapuera", "metro moema", "eucaliptos", "congonhas"]},
    "Campo Belo":    {"regiao": "zona_sul",   "apelidos": [], "refs": ["congonhas", "aeroporto", "metro campo belo"]},
    "Vila Mariana":  {"regiao": "zona_sul",   "apelidos": [], "refs": ["ana rosa", "metro ana rosa", "santa cruz", "ibirapuera", "unifesp"]},
    "Itaim Bibi":    {"regiao": "zona_sul",   "apelidos": ["itaim"], "refs": ["faria lima", "jk iguatemi", "vila olimpia", "juscelino kubitschek", "brigadeiro faria lima"]},
    "Pinheiros":     {"regiao": "zona_oeste", "apelidos": ["pinheiro"], "refs": ["faria lima", "largo da batata", "metro faria lima", "fradique coutinho", "oscar freire", "vila madalena"]},
    "Perdizes":      {"regiao": "zona_oeste", "apelidos": [], "refs": ["pompeia", "allianz parque", "puc", "sumare", "metro sumare"]},
    "Lapa":          {"regiao": "zona_oeste", "apelidos": [], "refs": ["bourbon shopping", "estacao lapa", "barra funda", "vila leopoldina"]},
    "Butantã":       {"regiao": "zona_oeste", "apelidos": ["butanta"], "refs": ["usp", "cidade universitaria", "metro butanta", "vila sonia"]},
    "Santana":       {"regiao": "zona_norte", "apelidos": [], "refs": ["metro santana", "parque da juventude", "expo center norte", "carandiru"]},
    "Tucuruvi":      {"regiao": "zona_norte", "apelidos": [], "refs": ["metro tucuruvi", "shopping metro tucuruvi", "jacana"]},
    "Casa Verde":    {"regiao": "zona_norte", "apelidos": [], "refs": ["ponte casa verde", "limao", "freguesia do o"]},
    "Tatuapé":       {"regiao": "zona_leste", "apelidos": ["tatuape"], "refs": ["metro tatuape", "shopping metro tatuape", "boulevard tatuape"]},
    "Anália Franco": {"regiao": "zona_leste", "apelidos": ["analia franco"], "refs": ["shopping analia franco", "parque ceret", "vila formosa"]},
    "Mooca":         {"regiao": "zona_leste", "apelidos": ["moóca"], "refs": ["shopping mooca", "parque da mooca", "bras"]},
    "República":     {"regiao": "centro",     "apelidos": ["republica", "centro velho"], "refs": ["metro republica", "avenida sao joao", "santa ifigenia", "anhangabau"]},
    "Bela Vista":    {"regiao": "centro",     "apelidos": ["bixiga", "bela vista"], "refs": ["paulista", "avenida paulista", "metro brigadeiro", "trianon"]},
    "Consolação":    {"regiao": "centro",     "apelidos": ["consolacao"], "refs": ["paulista", "avenida paulista", "metro consolacao", "rua augusta", "higienopolis"]},
}

REGIOES: dict[str, list[str]] = {
    "zona_sul": ["zona sul", "sul", "zs"],
    "zona_oeste": ["zona oeste", "oeste", "zo"],
    "zona_norte": ["zona norte", "norte", "zn"],
    "zona_leste": ["zona leste", "leste", "zl"],
    "centro": ["centro", "centro expandido", "região central"],
}

CIDADES_ATENDIDAS = ["sao paulo", "sp", "são paulo", "capital", "sampa"]
# Cidades vizinhas que o cliente cita e NÃO atendemos: a região sugerida é a mais próxima da capital.
FORA_DE_COBERTURA: dict[str, str] = {
    "osasco": "zona_oeste", "barueri": "zona_oeste", "alphaville": "zona_oeste", "carapicuiba": "zona_oeste",
    "guarulhos": "zona_norte", "santo andre": "zona_leste", "sao bernardo": "zona_sul", "sao caetano": "zona_leste",
    "diadema": "zona_sul", "taboao da serra": "zona_oeste", "cotia": "zona_oeste", "maua": "zona_leste",
    "abc": "zona_sul", "grande sao paulo": "", "interior": "",
}


def normalizar(texto: str) -> str:
    """minúsculo, sem acento, sem pontuação — a forma em que tudo é comparado."""
    t = unicodedata.normalize("NFKD", texto or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", t)).strip()


@dataclass
class Local:
    """O que o cliente quis dizer. `tipo` guia a busca; `confianca` diz o quanto dá para confiar."""
    tipo: str                                   # bairro | regiao | cidade | fora | desconhecido
    bairros: list[str] = field(default_factory=list)
    regiao: str | None = None
    cidade: str | None = None
    termo: str = ""                             # o que o cliente escreveu
    via: str = ""                               # exato | apelido | referencia | aproximado | regiao | cidade
    confianca: float = 0.0
    sugestao_regiao: str | None = None          # para fora de cobertura: a região atendida mais próxima


_IDX_BAIRRO: dict[str, str] = {}
for _b, _d in BAIRROS.items():
    _IDX_BAIRRO[normalizar(_b)] = _b
    for _a in _d["apelidos"]:
        _IDX_BAIRRO.setdefault(normalizar(_a), _b)
_IDX_REF: dict[str, list[str]] = {}
for _b, _d in BAIRROS.items():
    for _r in _d["refs"]:
        _IDX_REF.setdefault(normalizar(_r), []).append(_b)
_IDX_REGIAO: dict[str, str] = {normalizar(a): r for r, apel in REGIOES.items() for a in apel}
_IDX_REGIAO.update({normalizar(r): r for r in REGIOES})


def bairros_da_regiao(regiao: str | None) -> list[str]:
    return [b for b, d in BAIRROS.items() if d["regiao"] == regiao] if regiao else []


def vizinhos(bairro: str) -> list[str]:
    """Bairros que o cliente aceitaria como alternativa: mesma região, citados como referência entre si."""
    d = BAIRROS.get(bairro)
    if not d:
        return []
    refs = {normalizar(r) for r in d["refs"]}
    proximos = [b for b in bairros_da_regiao(d["regiao"]) if b != bairro]
    # quem aparece como referência do outro entra primeiro (Pinheiros ↔ Vila Madalena, Itaim ↔ Faria Lima)
    proximos.sort(key=lambda b: 0 if normalizar(b) in refs or refs & {normalizar(x) for x in BAIRROS[b]["refs"]} else 1)
    return proximos


def resolver(texto: str) -> Local:
    """Descobre o que o cliente quis dizer com um local. Nunca levanta exceção."""
    bruto = (texto or "").strip()
    t = normalizar(bruto)
    if not t:
        return Local(tipo="desconhecido", termo=bruto)

    if b := _IDX_BAIRRO.get(t):                                     # "Pinheiros", "itaim"
        return Local(tipo="bairro", bairros=[b], regiao=BAIRROS[b]["regiao"], cidade=CIDADE_PADRAO,
                     termo=bruto, via="exato", confianca=1.0)
    if r := _IDX_REGIAO.get(t):                                     # "zona sul"
        return Local(tipo="regiao", regiao=r, bairros=bairros_da_regiao(r), cidade=CIDADE_PADRAO,
                     termo=bruto, via="regiao", confianca=0.95)
    if t in CIDADES_ATENDIDAS:
        return Local(tipo="cidade", cidade=CIDADE_PADRAO, termo=bruto, via="cidade", confianca=0.9)
    for fora, sugestao in FORA_DE_COBERTURA.items():
        if re.search(rf"\b{re.escape(fora)}\b", t):
            return Local(tipo="fora", termo=bruto, via="cidade", confianca=0.9,
                         sugestao_regiao=sugestao or None, cidade=fora.title())
    if bs := _IDX_REF.get(t):                                       # "faria lima", "ibirapuera"
        return Local(tipo="bairro", bairros=bs, regiao=BAIRROS[bs[0]]["regiao"], cidade=CIDADE_PADRAO,
                     termo=bruto, via="referencia", confianca=0.8)

    # Frase inteira: procura qualquer bairro/apelido/referência/região mencionado dentro dela
    if achados := _varrer(t):
        return achados

    # Erro de digitação: "pinheros", "morumbo"
    if perto := get_close_matches(t, list(_IDX_BAIRRO), n=1, cutoff=0.82):
        b = _IDX_BAIRRO[perto[0]]
        return Local(tipo="bairro", bairros=[b], regiao=BAIRROS[b]["regiao"], cidade=CIDADE_PADRAO,
                     termo=bruto, via="aproximado", confianca=0.65)
    return Local(tipo="desconhecido", termo=bruto, confianca=0.0)


def _varrer(t: str) -> Local | None:
    """Encontra locais dentro de uma frase ('quero em pinheiros perto do metrô')."""
    palavras = t.split()
    janelas = [" ".join(palavras[i:i + n]) for n in (3, 2, 1) for i in range(len(palavras) - n + 1)]
    for j in janelas:
        if b := _IDX_BAIRRO.get(j):
            return Local(tipo="bairro", bairros=[b], regiao=BAIRROS[b]["regiao"], cidade=CIDADE_PADRAO,
                         termo=j, via="exato", confianca=0.9)
    for j in janelas:
        if bs := _IDX_REF.get(j):
            return Local(tipo="bairro", bairros=bs, regiao=BAIRROS[bs[0]]["regiao"], cidade=CIDADE_PADRAO,
                         termo=j, via="referencia", confianca=0.75)
    for j in janelas:
        if r := _IDX_REGIAO.get(j):
            return Local(tipo="regiao", regiao=r, bairros=bairros_da_regiao(r), cidade=CIDADE_PADRAO,
                         termo=j, via="regiao", confianca=0.85)
    return None


def resolver_varios(textos: list[str]) -> list[Local]:
    return [l for l in (resolver(t) for t in textos if t) if l.tipo != "desconhecido"]


def descrever(local: Local) -> str:
    """Como o agente deve se referir ao local — usado nos prompts."""
    if local.tipo == "bairro":
        return ", ".join(local.bairros)
    if local.tipo == "regiao":
        return (local.regiao or "").replace("zona_", "zona ").replace("centro", "centro")
    if local.tipo == "cidade":
        return local.cidade or CIDADE_PADRAO
    return local.termo
