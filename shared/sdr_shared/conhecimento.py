"""Base de conhecimento institucional: fatiar documentos e buscar o trecho certo.

Este módulo existe por causa de uma pergunta que a Mora não sabia responder: *"vocês cobram taxa de
visita?"*. O catálogo não responde, e o modelo sozinho **inventaria** — que é o pior desfecho
possível, porque uma política inventada só é desmentida depois, pelo corretor, na frente do cliente.

Duas decisões carregam o arquivo:

1. **Fatiar por cabeçalho, não por tamanho.** Um FAQ é uma lista de perguntas; cada `##` já é a
   unidade de sentido. Cortar a cada N caracteres partiria a resposta ao meio e traria metade dela.
   Só quando a seção é longa demais é que entra o corte por tamanho — e aí o cabeçalho vai junto em
   cada pedaço, senão o trecho chega sem dizer do que trata.

2. **Piso de similaridade.** Busca vetorial SEMPRE devolve os vizinhos mais próximos, mesmo quando
   o mais próximo está longe. Sem piso, perguntar sobre pets traz o trecho de financiamento e o
   agente responde com confiança sobre o assunto errado. É a falha clássica de RAG, e ela não
   aparece em teste feliz: aparece na primeira pergunta que o corpus não cobre.
"""
import re
from dataclasses import dataclass

CABECALHO = re.compile(r"^(#{1,4})\s+(.+?)\s*$", re.M)
MAX_CHARS = 1200          # acima disso, a seção é dividida — com o cabeçalho repetido em cada parte
MIN_CHARS = 40            # abaixo disso não é trecho, é sobra de formatação

# Piso de similaridade cosseno. 0,35 saiu de calibrar contra perguntas que o corpus NÃO cobre
# ("vocês vendem carro?"): abaixo disso o melhor resultado já era assunto alheio. É deliberadamente
# generoso — errar para o lado de "não sei" custa uma pergunta a mais ao cliente; errar para o outro
# lado custa uma informação falsa sobre a empresa.
PISO_SIMILARIDADE = 0.35


@dataclass(frozen=True)
class Trecho:
    id: str
    arquivo: str
    assunto: str
    titulo: str | None
    texto: str
    ordem: int
    score: float = 0.0

    @property
    def fonte(self) -> str:
        """Como a fonte é citada ao cliente. O nome do arquivo em si não diz nada a ninguém."""
        return self.titulo or self.arquivo.replace("-", " ").removesuffix(".md").capitalize()


def _limpar(texto: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", texto).strip()


def fatiar(conteudo: str, arquivo: str, assunto: str) -> list[Trecho]:
    """Divide o documento em trechos, cada um carregando o próprio cabeçalho.

    O texto antes do primeiro cabeçalho (título do arquivo, nota de contexto) vira o trecho zero:
    é onde costuma estar o aviso de que o documento é de exemplo, e perder isso seria perder a
    ressalva junto com o conteúdo.
    """
    marcas = list(CABECALHO.finditer(conteudo))
    if not marcas:
        return _dividir(_limpar(conteudo), arquivo, assunto, None, 0)

    trechos: list[Trecho] = []
    ordem = 0
    if (preambulo := _limpar(conteudo[: marcas[0].start()])) and len(preambulo) >= MIN_CHARS:
        trechos += _dividir(preambulo, arquivo, assunto, None, ordem)
        ordem = len(trechos)

    for i, m in enumerate(marcas):
        fim = marcas[i + 1].start() if i + 1 < len(marcas) else len(conteudo)
        titulo = m.group(2).strip()
        corpo = _limpar(conteudo[m.end():fim])
        if not corpo:
            continue          # cabeçalho de seção que só agrupa outros; o conteúdo vem nos filhos
        novos = _dividir(f"{titulo}\n{corpo}", arquivo, assunto, titulo, ordem)
        trechos += novos
        ordem += len(novos)
    return trechos


def _dividir(texto: str, arquivo: str, assunto: str, titulo: str | None, inicio: int) -> list[Trecho]:
    if len(texto) <= MAX_CHARS:
        return [Trecho(id=f"{arquivo}#{inicio}", arquivo=arquivo, assunto=assunto, titulo=titulo,
                       texto=texto, ordem=inicio)] if len(texto) >= MIN_CHARS else []
    partes, atual = [], []
    tamanho = 0
    for paragrafo in texto.split("\n\n"):
        if tamanho + len(paragrafo) > MAX_CHARS and atual:
            partes.append("\n\n".join(atual))
            # O cabeçalho vai junto em cada pedaço: sem ele, a segunda metade de "Taxas de locação"
            # chega ao modelo como um parágrafo solto sobre números, sem dizer de que se trata.
            atual, tamanho = ([titulo] if titulo else []), len(titulo or "")
        atual.append(paragrafo)
        tamanho += len(paragrafo)
    if atual:
        partes.append("\n\n".join(atual))
    return [Trecho(id=f"{arquivo}#{inicio + i}", arquivo=arquivo, assunto=assunto, titulo=titulo,
                   texto=p, ordem=inicio + i)
            for i, p in enumerate(partes) if len(p) >= MIN_CHARS]


def acima_do_piso(trechos: list[Trecho], piso: float = PISO_SIMILARIDADE) -> list[Trecho]:
    """Filtra pelo piso e devolve na ordem de relevância. Lista vazia é resposta legítima — e o nó
    que consome precisa tratá-la como 'não sei', nunca como 'responda assim mesmo'."""
    return [t for t in trechos if t.score >= piso]
