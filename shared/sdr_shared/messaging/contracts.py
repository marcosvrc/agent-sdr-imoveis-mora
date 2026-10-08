"""Contratos entre canais ⇄ agente ⇄ scheduler. Mudar aqui é mudar a API interna do sistema."""
import json
import re
from datetime import datetime, timezone
from enum import StrEnum
from pydantic import BaseModel, Field, field_validator
from ..models.imovel import ImovelCard


class Canal(StrEnum):
    TELEGRAM = "telegram"
    WEB = "web"
    SISTEMA = "sistema"      # follow-up, eventos internos


class TipoMensagem(StrEnum):
    TEXTO = "texto"
    AUDIO = "audio"
    LOCALIZACAO = "localizacao"
    BOTAO = "botao"
    FOLLOWUP = "followup"      # gerado pelo scheduler
    REATIVACAO = "reativacao"  # gerado pelo reativador: entrou um imóvel que casa com um lead antigo


# Turnos que a Mora começa sozinha, sem ninguém do outro lado ter escrito nada. Valem regras
# diferentes: não contam para a vazão (não é o cliente digitando), não viram mensagem "in" no
# histórico e não atualizam `ultima_mensagem_em` — carimbar atividade aqui apagaria justamente o
# silêncio que motivou o contato, e o próximo aviso sairia como se a pessoa tivesse respondido.
INICIADAS_PELO_AGENTE = frozenset({TipoMensagem.FOLLOWUP, TipoMensagem.REATIVACAO})


INVISIVEIS = frozenset(range(0x200B, 0x2010)) | frozenset(range(0x2060, 0x2065)) | {0xFEFF, 0x00AD}


def _imprimivel(ch: str) -> bool:
    codigo = ord(ch)
    if ch in "\n\t":
        return True
    return codigo >= 32 and codigo != 0x7F and codigo not in INVISIVEIS


# Formato de id de imóvel aceito do lado de fora (botão do site, deep link, evento de navegação).
# Um só regex, aqui, para o `/eventos` da API e o handler do agente não divergirem. Use fullmatch:
# com `match`, o `$` aceita um "\n" no fim.
ID_IMOVEL = re.compile(r"[A-Za-z0-9_-]{1,64}")

MAX_CONTEUDO = 4000        # ninguém descreve o imóvel que procura em mais que isso; acima é abuso ou erro
MAX_ID = 128
# Teto do `meta`. O do Telegram (nome, chat_id, file_id, lat/lng, imovel_origem) e o do site
# (imovel_origem, saudacao_exibida, botao) ficam em poucas centenas de bytes; o do reativador
# (motivos, pontos), abaixo de 1 KB. Sem teto, o navegador mandava qualquer dicionário, e ele ia
# inteiro para `mensagens.meta` a cada turno.
MAX_META_CHAVES = 16
MAX_META_BYTES = 2048


class MensagemNormalizada(BaseModel):
    """Entrada do agente. Todo canal produz isto; o agente nunca vê o payload bruto.

    Os limites ficam aqui, no contrato, e não em cada canal: é o único ponto por onde toda
    mensagem passa, venha do Telegram, da web ou de um teste.
    """
    lead_id: str = Field(max_length=MAX_ID)
    canal: Canal
    identificador_canal: str = Field(max_length=MAX_ID)   # telefone E.164 ou session_id
    tipo: TipoMensagem = TipoMensagem.TEXTO
    conteudo: str = Field(max_length=MAX_CONTEUDO)        # texto, transcrição do áudio, id do botão...
    meta: dict = Field(default_factory=dict)              # imovel_origem, lat/long, nome do perfil...
    recebida_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("conteudo", mode="before")
    @classmethod
    def _truncar(cls, v):
        """Trunca em vez de rejeitar: uma mensagem enorme é um cliente colando um anúncio inteiro
        muito mais vezes do que é um ataque — e recusar o turno deixaria a pessoa sem resposta."""
        if isinstance(v, str) and len(v) > MAX_CONTEUDO:
            return v[:MAX_CONTEUDO]
        return v

    @field_validator("meta")
    @classmethod
    def _meta_com_teto(cls, v: dict) -> dict:
        """Recusa em vez de truncar: nenhum canal legítimo chega perto, e cortar um JSON no meio
        produziria um `meta` que ninguém mandou."""
        if len(v) > MAX_META_CHAVES:
            raise ValueError(f"meta com mais de {MAX_META_CHAVES} campos")
        if len(json.dumps(v, ensure_ascii=False, default=str).encode()) > MAX_META_BYTES:
            raise ValueError(f"meta acima de {MAX_META_BYTES} bytes")
        return v

    @field_validator("conteudo", "identificador_canal", "lead_id", mode="before")
    @classmethod
    def _sem_controle(cls, v):
        """Remove controles e invisíveis — usados para esconder instruções dentro de um texto inocente."""
        if not isinstance(v, str):
            return v
        return "".join(ch for ch in v if _imprimivel(ch))



class Acao(StrEnum):
    NENHUMA = "nenhuma"
    AGENDAR = "agendar"
    HANDOFF = "handoff"
    ENCERRAR = "encerrar"


class RespostaAgente(BaseModel):
    """Saída do agente. Neutra: o canal decide como renderizar."""
    lead_id: str
    texto: str
    opcoes: list[str] = Field(default_factory=list)       # ≤3 → botões do canal; >3 → lista
    imoveis: list[ImovelCard] = Field(default_factory=list)
    acao: Acao = Acao.NENHUMA
    dados: dict = Field(default_factory=dict)             # detalhes da ação (ex.: visita confirmada) — o canal renderiza


class EventoDominio(BaseModel):
    """Evento de domínio publicado no broker (`sdr-events`)."""
    tipo: str            # lead.created | lead.stage_changed | lead.inactive | visit.scheduled
    lead_id: str
    dados: dict = Field(default_factory=dict)
    em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
