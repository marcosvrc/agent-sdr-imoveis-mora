"""Carregamento dos datasets e comparação de valores.

A comparação é objetiva de propósito: nada aqui usa um LLM para julgar. Onde a resposta certa é
ambígua (texto livre como `urgencia`), o dataset declara as formas aceitáveis com `{"qualquer": [...]}`
em vez de delegar a decisão a um juiz — juiz-LLM tem o próprio erro, e num harness pequeno esse erro
vira o número que você está medindo.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

DIR = Path(__file__).parent / "datasets"


@dataclass
class Caso:
    id: str
    dados: dict

    def __getitem__(self, chave):
        return self.dados[chave]

    def get(self, chave, padrao=None):
        return self.dados.get(chave, padrao)


@dataclass
class Resultado:
    caso: str
    passou: bool
    detalhe: str = ""
    extras: dict = field(default_factory=dict)


def carregar(nome: str) -> list[Caso]:
    """Lê um .jsonl ignorando linhas vazias e comentários (`//`), para o dataset poder se explicar."""
    arquivo = DIR / f"{nome}.jsonl"
    casos = []
    for linha in arquivo.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if not linha or linha.startswith("//"):
            continue
        d = json.loads(linha)
        casos.append(Caso(id=d["id"], dados=d))
    return casos


def normalizar(v) -> str:
    """Sem acento, minúsculo, espaço colapsado — 'Zona Sul' e 'zona sul' são a mesma resposta."""
    if v is None:
        return ""
    s = unicodedata.normalize("NFKD", str(v)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", s).strip().lower()


def combina(esperado, obtido) -> bool:
    """Um campo extraído bate com o gabarito?

    - número: tolerância pequena (o modelo devolve 800000.0 onde o gabarito diz 800000)
    - lista: cada item do gabarito precisa aparecer em ALGUM item do obtido (o modelo pode achar
      bairros a mais, e requisito copiado das palavras do cliente varia na borda — "aceita cachorro"
      e "só serve se aceitar cachorro" são a mesma resposta, então o gabarito pede o miolo)
    - texto: igual ou contido, normalizado — 'imediata' aceita 'urgência imediata'
    - {"qualquer": [...]}: qualquer uma das formas serve
    """
    if isinstance(esperado, dict) and "qualquer" in esperado:
        return any(combina(e, obtido) for e in esperado["qualquer"])
    if isinstance(esperado, bool):
        return bool(obtido) is esperado
    if isinstance(esperado, (int, float)):
        try:
            return abs(float(obtido) - float(esperado)) < 0.01
        except (TypeError, ValueError):
            return False
    if isinstance(esperado, list):
        obtidos = [normalizar(x) for x in (obtido or [])]
        return all(any(normalizar(e) in o for o in obtidos) for e in esperado) if esperado else not obtidos
    e, o = normalizar(esperado), normalizar(obtido)
    return bool(o) and (e == o or e in o)


def vazio(v) -> bool:
    """O que conta como 'o modelo não preencheu'. Intencao.INDEFINIDA é vazio: é o default do cartão."""
    return v in (None, "", [], 0, False) or normalizar(v) == "indefinida"
