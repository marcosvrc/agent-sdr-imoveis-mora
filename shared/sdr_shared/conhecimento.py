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

# NÃO existe piso léxico, e a ausência é uma decisão medida.
#
# A primeira versão deixava um trecho passar por casamento léxico forte mesmo com cosseno baixo — a
# ideia sendo que "o cliente usou a palavra do documento" é evidência forte. Com a consulta ligando
# os termos por E, as negativas davam ts_rank_cd exatamente 0.0 e o atalho parecia gratuito.
#
# Ao trocar para OU (que é o que faz o léxico funcionar de verdade), as negativas passaram a
# pontuar: 7 de 10 acima de zero, chegando a 0,2 — porque quase toda pergunta em português
# compartilha alguma palavra com algum trecho. Nessa escala o sinal léxico sozinho não separa
# pergunta coberta de pergunta não coberta, e o atalho viraria uma porta aberta para responder o
# que não se sabe.
#
# O léxico continua valendo para ORDENAR (a fusão RRF), que é onde ele é confiável. Quem decide
# entre responder e calar continua sendo o cosseno, sozinho.


@dataclass(frozen=True)
class Trecho:
    id: str
    arquivo: str
    assunto: str
    titulo: str | None
    texto: str
    ordem: int
    score: float = 0.0
    # Sinal léxico (ts_rank_cd). Separado do cosseno de propósito: são escalas diferentes, e somá-los
    # num número só esconderia qual dos dois trouxe o trecho.
    lexico: float = 0.0

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


# Conectivos que abrem uma pergunta dependente do que veio antes, e anáforas que não têm a que se
# referir sozinhas. Lista curta de propósito: cada entrada aqui é uma chance de reescrever uma
# pergunta que não precisava, e reescrever demais é tão ruim quanto de menos.
# Escritos SEM acento: a comparação acontece depois de `_sem_acento`, e listar as duas grafias
# deixaria a normalização sem função — dois mecanismos para a mesma coisa, nenhum deles testável,
# porque remover um não quebra nada. Apareceu numa mutação que passou quando não devia.
_CONECTIVOS = ("e ", "mas ", "entao ", "ai ", "ok ", "certo ", "e se ", "e quanto ")
_ANAFORAS = frozenset({"isso", "isto", "aquilo", "ele", "ela", "eles", "elas", "la", "disso",
                       "dele", "dela", "nesse", "nisso", "esse", "essa", "mesmo", "tambem"})
MIN_PALAVRAS_AUTONOMA = 4


def _sem_acento(texto: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")


def depende_do_contexto(pergunta: str) -> bool:
    """A pergunta se sustenta sozinha como consulta de busca?

    Três sinais, e basta um: começa por conectivo ("e se eu sair antes?"), contém anáfora sem
    antecedente ("quanto custa isso?"), ou é curta demais para ter assunto ("e a multa?").

    O ponto não é entender a frase — é decidir se vale carregar o assunto anterior para dentro dela.
    Errar para "depende" custa algumas palavras a mais no embedding; errar para o outro lado manda
    ao banco uma consulta sem assunto nenhum, e a busca vetorial sempre devolve ALGO.
    """
    limpo = _sem_acento((pergunta or "").strip().lower())
    if not limpo:
        return False
    if limpo.startswith(_CONECTIVOS):
        return True
    palavras = [p for p in "".join(c if c.isalnum() else " " for c in limpo).split() if len(p) > 2]
    if any(p in _ANAFORAS for p in palavras):
        return True
    return len(palavras) < MIN_PALAVRAS_AUTONOMA


def reescrever_pergunta(pergunta: str, anteriores: list[str] | None = None) -> str:
    """Consulta de busca para a pergunta atual, trazendo o assunto anterior quando ela depende dele.

    Determinística de propósito. Um reescritor com LLM acertaria mais casos e custaria uma chamada
    a mais por turno, num caminho onde o cliente está esperando — e passaria a ser mais uma coisa
    que pode alucinar bem na frente da busca. Aqui é concatenação: a pergunta que não se sustenta
    sozinha herda a última que se sustentava.

    O texto atual vem PRIMEIRO. A ordem importa pouco para um saco de palavras, mas importa para
    modelos que pesam posição, e o que o cliente acabou de perguntar é o que ele quer saber.
    """
    atual = (pergunta or "").strip()
    if not atual or not anteriores or not depende_do_contexto(atual):
        return atual
    ancora = next((a.strip() for a in reversed(anteriores)
                   if a and a.strip() and not depende_do_contexto(a)), "")
    return f"{atual} {ancora}".strip() if ancora else atual


def acima_do_piso(trechos: list[Trecho], piso: float = PISO_SIMILARIDADE) -> list[Trecho]:
    """Filtra pelo piso e devolve na ordem de relevância. Lista vazia é resposta legítima — e o nó
    que consome precisa tratá-la como 'não sei', nunca como 'responda assim mesmo'.

    Decide pelo cosseno, e só por ele — veja a nota em PISO_LEXICO para o porquê de o sinal léxico
    não valer como salvo-conduto.
    """
    return [t for t in trechos if t.score >= piso]
