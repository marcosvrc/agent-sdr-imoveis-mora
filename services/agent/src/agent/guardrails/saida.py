"""Última barreira: o que o modelo escreveu antes de virar mensagem para o cliente.

Nada aqui depende do modelo ter obedecido ao prompt — é justamente para quando ele não obedeceu.
Três coisas não podem sair: pedaço das instruções internas, dado pessoal que ninguém pediu, e
o formato técnico (tags, JSON, código) que denuncia um vazamento de raciocínio interno.
"""
import logging
import re

log = logging.getLogger("agent.guardrails")

# Trechos que só existem nas nossas instruções. Se aparecerem na resposta, houve vazamento.
VAZAMENTO = re.compile(r"""(
    regras\s+de\s+seguranca
  | \bsystem\s*prompt\b | prompt\s+do\s+sistema
  | <<<\s*(fim_)?(cliente|dado) | \b(CLIENTE|DADO)_[0-9a-f]{8}
  | minhas\s+instru[cç][õo]es\s+(dizem|s[ãa]o)
  | fui\s+(instru[ií]do|configurado|programado)\s+(a|para|com)
  | (voc[eê]\s+[ée]|sou)\s+o\s+roteador\s+interno
  | cart[ãa]o\s+de\s+qualifica[cç][ãa]o
  | \b(qualificador|consultor|agendador|supervisor|resumidor)\s*\|\s*
  | OBRIGATORIOS_(COMPRA|INVESTIMENTO)
)""", re.X | re.I)

# PII que o agente não deve repetir de volta. O telefone do próprio cliente é exceção: confirmar
# "anotei o 11 98888-7777" é atendimento normal, e por isso telefone não entra aqui.
CPF = re.compile(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b")
CARTAO = re.compile(r"\b(?:\d[ -]?){13,19}\b")

FALLBACK = ("Deixa eu te ajudar direito: me conta o que você procura — comprar, alugar ou investir — "
            "e em que região?")


def _mascarar(texto: str) -> tuple[str, list[str]]:
    achados = []
    if CPF.search(texto):
        texto, achados = CPF.sub("[documento omitido]", texto), [*achados, "cpf"]
    if CARTAO.search(texto):
        texto, achados = CARTAO.sub("[número omitido]", texto), [*achados, "cartao"]
    return texto, achados


def sanear(texto: str, lead_id: str = "") -> str:
    """Devolve o texto seguro para enviar. Em caso de vazamento, troca a resposta inteira."""
    from ..util import limpar_texto

    bruto = texto if isinstance(texto, str) else str(texto)
    limpo = limpar_texto(texto)
    # o bruto também é inspecionado: limpar_texto apaga marcadores internos, e apagá-los não é
    # o mesmo que descartar a resposta que os continha
    if VAZAMENTO.search(bruto) or VAZAMENTO.search(limpo):
        log.error("resposta descartada por vazamento de instruções lead=%s", lead_id)
        _auditar(lead_id, "vazamento_de_prompt", limpo[:300])
        return FALLBACK

    limpo, achados = _mascarar(limpo)
    if achados:
        log.warning("PII mascarada na resposta lead=%s %s", lead_id, achados)
        _auditar(lead_id, "pii_na_resposta", ", ".join(achados))
    return limpo or FALLBACK


def _auditar(lead_id: str, categoria: str, detalhe: str) -> None:
    from sdr_shared.db import auditar
    auditar(acao="agente.saida_barrada", entidade="lead", entidade_id=lead_id or None, ator_tipo="sistema",
            ator_nome="guardrails", resultado="erro", detalhe=detalhe, dados={"categoria": categoria})
