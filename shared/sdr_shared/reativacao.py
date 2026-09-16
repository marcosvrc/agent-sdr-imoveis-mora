"""Reativação proativa: imóvel novo → leads antigos que pediram exatamente aquilo.

A busca do agente vai do lead para o imóvel. Esta vai ao contrário: entrou um imóvel no catálogo,
quem estava procurando isso? É o que um bom SDR humano faz — liga porque tem novidade, não para
perguntar "ainda tem interesse?".

**Por que casamento determinístico e não embedding.** O cartão de qualificação é estruturado
(intenção, região, bairros, faixa de preço, quartos, tipo). Contra campos estruturados, filtro exato
ganha de similaridade semântica: é mais barato, roda sem o embedder no ar, dá o mesmo resultado toda
vez e — o que mais importa aqui — produz o MOTIVO em português, que vai virar a primeira frase da
mensagem. "R$ 20 mil abaixo do teto que você me deu" é verificável; "similaridade 0,87" não é.

**Este módulo não envia nada.** Ele responde "quem avisaríamos, e por quê" — e, para quem ficou de
fora, por que ficou. Enviar é decisão de outra camada, com cadência e orçamento (ver ADR).
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from .models import Imovel, Intencao, Lead

# Quanto tempo sem conversar para o lead ser "antigo" a ponto de a notícia ter valor. Abaixo disso,
# ele está em atendimento e a Mora fala com ele na conversa mesmo.
DIAS_SILENCIO = 3
# Um aviso por semana por lead, no máximo. É o limite entre serviço e spam.
DIAS_ENTRE_REATIVACOES = 7
# Piso de pontuação: bater só na operação não é notícia, é catálogo.
PONTOS_MINIMOS = 60


@dataclass
class Candidato:
    lead: Lead
    pontos: int
    motivos: list[str] = field(default_factory=list)

    def resumo(self) -> dict:
        return {"lead_id": self.lead.id, "nome": self.lead.nome, "telefone": self.lead.telefone,
                "temperatura": str(self.lead.temperatura), "score": self.lead.score,
                "estagio": str(self.lead.estagio), "pontos": self.pontos, "motivos": self.motivos}


@dataclass
class Excluido:
    lead: Lead
    motivo: str

    def resumo(self) -> dict:
        return {"lead_id": self.lead.id, "nome": self.lead.nome, "motivo": self.motivo}


def _operacao_desejada(intencao: Intencao) -> str | None:
    """Investidor compra: `investimento` procura imóvel à venda, não aluguel."""
    return {Intencao.COMPRA: "venda", Intencao.INVESTIMENTO: "venda", Intencao.ALUGUEL: "aluguel"}.get(intencao)


def pontuar(lead: Lead, im: Imovel) -> tuple[int, list[str]]:
    """Quanto este imóvel casa com o que o lead pediu, e em português por quê.

    Devolve (0, [...]) quando algo essencial não bate — operação, teto de preço ou quartos são
    eliminatórios, porque errá-los transforma a notícia em incômodo.
    """
    c = lead.cartao
    motivos: list[str] = []

    desejada = _operacao_desejada(c.intencao)
    if desejada and im.operacao != desejada:
        return 0, [f"o lead procura {desejada} e o imóvel é de {im.operacao}"]
    if not desejada:
        return 0, ["intenção do lead ainda indefinida"]

    if c.preco_max and im.preco > c.preco_max:
        return 0, [f"acima do teto de R$ {c.preco_max:,.0f}".replace(",", ".")]
    if c.preco_min and im.preco < c.preco_min:
        return 0, [f"abaixo do piso de R$ {c.preco_min:,.0f}".replace(",", ".")]
    if c.quartos and im.quartos < c.quartos:
        return 0, [f"tem {im.quartos} quarto(s) e o lead pediu {c.quartos}+"]
    if c.tipo_imovel and im.tipo != c.tipo_imovel:
        return 0, [f"é {im.tipo} e o lead pediu {c.tipo_imovel}"]

    pontos = 30                                                    # passou nos eliminatórios
    motivos.append(f"{im.quartos} quarto(s), como pedido" if c.quartos else "dentro do perfil pedido")

    bairros = {b.lower() for b in c.bairros}
    if bairros and im.bairro.lower() in bairros:
        pontos += 40
        motivos.append(f"em {im.bairro}, um dos bairros que ele citou")
    elif c.regiao and im.regiao == c.regiao:
        pontos += 25
        motivos.append(f"na {c.regiao.replace('_', ' ')}, a região pedida")
    elif bairros or c.regiao:
        pontos += 5
        motivos.append(f"em {im.bairro} (fora da área que ele citou)")

    if c.preco_max:
        folga = c.preco_max - im.preco
        if folga > 0:
            # Abaixo do teto é o argumento mais forte que existe numa reativação.
            pontos += 25 if folga / c.preco_max >= 0.10 else 10
            motivos.append(f"R$ {folga:,.0f} abaixo do teto que ele deu".replace(",", "."))

    if c.tipo_imovel and im.tipo == c.tipo_imovel:
        pontos += 10
        motivos.append(f"é {im.tipo}, o tipo que ele queria")
    if c.urgencia == "imediata":
        pontos += 10
        motivos.append("ele disse que a urgência era imediata")
    if c.intencao == Intencao.INVESTIMENTO and im.destaque_investimento:
        pontos += 15
        motivos.append("marcado como indicado para investir, e ele procura investimento")

    return min(pontos, 100), motivos


def elegivel(lead: Lead, imovel_id: str, conhecidos: dict[str, set[str]],
             agora: datetime | None = None) -> str | None:
    """Motivo para NÃO avisar este lead, ou `None` quando pode.

    Devolver o motivo (em vez de um booleano) é o que permite a tela de simulação mostrar quem ficou
    de fora e por quê — que é onde se descobre que a regra está errada, antes de mandar mensagem.
    """
    agora = agora or datetime.now(timezone.utc)

    if lead.encerrado_em:
        return "oportunidade encerrada"
    if not lead.aceita_reativacao:
        return "pediu para não receber avisos"
    if str(lead.estagio) == "handoff":
        return "já está com um corretor"
    if not (lead.telefone or lead.email or lead.cartao.tem_contato()):
        return "sem canal de contato"

    for situacao, ids in conhecidos.items():
        if imovel_id in ids:
            return {"descartado": "já descartou este imóvel",
                    "visita_marcada": "já tem visita marcada para este imóvel"}.get(
                        situacao, "este imóvel já foi apresentado a ele")

    if lead.reativado_em and agora - lead.reativado_em < timedelta(days=DIAS_ENTRE_REATIVACOES):
        return f"já recebeu um aviso nos últimos {DIAS_ENTRE_REATIVACOES} dias"
    if lead.ultima_mensagem_em and agora - lead.ultima_mensagem_em < timedelta(days=DIAS_SILENCIO):
        return f"conversou há menos de {DIAS_SILENCIO} dias — a Mora fala com ele na conversa"
    return None


def avaliar(im: Imovel, leads: list[Lead], conhecidos_por_lead: dict[str, dict[str, set[str]]],
            agora: datetime | None = None, limite: int = 20) -> dict:
    """Simulação completa para um imóvel: quem seria avisado, quem não, e por quê.

    `conhecidos_por_lead` é {lead_id: {situacao: {imovel_id}}} — vem do InteresseRepository e evita
    uma consulta por lead.
    """
    candidatos: list[Candidato] = []
    excluidos: list[Excluido] = []

    for lead in leads:
        pontos, motivos = pontuar(lead, im)
        if pontos < PONTOS_MINIMOS:
            excluidos.append(Excluido(lead, motivos[0] if motivos else "não bate com o perfil"))
            continue
        if impedimento := elegivel(lead, im.id, conhecidos_por_lead.get(lead.id, {}), agora):
            excluidos.append(Excluido(lead, impedimento))
            continue
        candidatos.append(Candidato(lead, pontos, motivos))

    # Mais aderente primeiro; empate desempata pelo lead mais quente.
    candidatos.sort(key=lambda c: (c.pontos, c.lead.score), reverse=True)
    return {
        "imovel_id": im.id,
        "avaliados": len(leads),
        "candidatos": [c.resumo() for c in candidatos[:limite]],
        "excluidos": [e.resumo() for e in excluidos],
        "pontos_minimos": PONTOS_MINIMOS,
    }
