import re
from datetime import datetime, timezone
from enum import StrEnum
from typing import ClassVar
from pydantic import BaseModel, Field, field_validator

_CONTROLE = re.compile(r"[\x00-\x1f\x7f\u2028\u2029]")


def _limpar_identidade(valor: str | None, limite: int) -> str | None:
    """Nome/telefone chegam do cliente (meta do canal web, first_name do Telegram, extração do LLM)
    e são interpolados no prompt de sistema — sem passar pelo envelope de conteúdo não confiável.
    Quebra de linha ali deixa o texto do cliente parecendo uma instrução nova; por isso tiramos
    controles e cortamos o tamanho na entrada do modelo, não só na exibição."""
    if valor is None:
        return None
    limpo = _CONTROLE.sub(" ", str(valor))
    limpo = re.sub(r"\s+", " ", limpo).strip()[:limite]
    return limpo or None


class Intencao(StrEnum):
    COMPRA = "compra"
    ALUGUEL = "aluguel"
    INVESTIMENTO = "investimento"
    INDEFINIDA = "indefinida"


class Estagio(StrEnum):
    NOVO = "novo"
    QUALIFICANDO = "qualificando"
    QUALIFICADO = "qualificado"
    AGENDADO = "agendado"
    HANDOFF = "handoff"
    INATIVO = "inativo"
    FRIO = "frio"


class Temperatura(StrEnum):
    QUENTE = "quente"
    MORNO = "morno"
    FRIO = "frio"


class CartaoQualificacao(BaseModel):
    """Fonte de verdade da qualificação. O Qualificador conversa para preencher isto."""
    intencao: Intencao = Intencao.INDEFINIDA
    regiao: str | None = None
    bairros: list[str] = Field(default_factory=list)
    preco_min: float | None = None
    preco_max: float | None = None
    quartos: int | None = None
    tipo_imovel: str | None = None          # apartamento, casa, studio...
    urgencia: str | None = None             # imediata, 3 meses, 6 meses, sem prazo
    # Investidor
    perfil_investidor: str | None = None    # conservador, moderado, arrojado
    ticket: float | None = None
    retorno_esperado: str | None = None
    # Contato — pedido progressivamente, nunca tudo de uma vez (ver prompts/qualificador.md)
    nome_informado: str | None = None
    telefone_informado: str | None = None
    email_informado: str | None = None
    # Sinais
    imoveis_visualizados: list[str] = Field(default_factory=list)
    pediu_visita: bool = False

    OBRIGATORIOS_COMPRA_ALUGUEL: ClassVar[tuple[str, ...]] = ("intencao", "regiao", "preco_max", "quartos", "urgencia")
    OBRIGATORIOS_INVESTIMENTO: ClassVar[tuple[str, ...]] = ("intencao", "perfil_investidor", "ticket", "retorno_esperado")

    # O cartão inteiro é interpolado no prompt do consultor/follow-up/resumidor sem envelope, e o
    # que está nele saiu do texto do cliente (via extração do LLM). Mesmo tratamento do nome:
    # sem quebra de linha e com tamanho limitado, para não virar instrução no meio do prompt.
    @field_validator("regiao", "tipo_imovel", "urgencia", "perfil_investidor", "retorno_esperado",
                     "nome_informado", "telefone_informado", "email_informado", mode="before")
    @classmethod
    def _texto_livre_sem_veneno(cls, v):
        return _limpar_identidade(v, 120)

    @field_validator("bairros", mode="before")
    @classmethod
    def _bairros_sem_veneno(cls, v):
        if not isinstance(v, list):
            return v
        return [b for b in (_limpar_identidade(x, 80) for x in v) if b][:20]

    def tem_contato(self) -> bool:
        """Um lead só é aproveitável pelo corretor se der para falar com ele."""
        return bool(self.telefone_informado or self.email_informado)

    def campos_faltantes(self) -> list[str]:
        campos = (self.OBRIGATORIOS_INVESTIMENTO if self.intencao == Intencao.INVESTIMENTO
                  else self.OBRIGATORIOS_COMPRA_ALUGUEL)
        return [c for c in campos if getattr(self, c) in (None, Intencao.INDEFINIDA)]

    def completo(self) -> bool:
        return not self.campos_faltantes()


class AnaliseLead(BaseModel):
    """Análise da conversa para o corretor: sentimento e perfil de comunicação/decisão INFERIDOS do texto.
    Não é avaliação clínica — só o que a conversa sustenta. Gerada pelo nó Resumidor (saída estruturada)."""
    sentimento: str = "neutro"                 # positivo | neutro | negativo | frustrado | ansioso | entusiasmado
    sentimento_tendencia: str = "estavel"      # melhorando | estavel | piorando
    confianca: float = 0.5                     # 0–1: quanto a conversa sustenta a leitura
    engajamento: str = "medio"                 # alto | medio | baixo
    perfil_decisao: str = "indefinido"         # objetivo | analitico | cauteloso | emocional | explorador | indefinido
    estilo_comunicacao: str = ""               # ex.: "curto e direto, informal, responde rápido"
    motivadores: list[str] = Field(default_factory=list)      # o que move a decisão (localização, preço, prazo, família...)
    objecoes: list[str] = Field(default_factory=list)         # dúvidas/objeções explícitas ou implícitas
    sinais_alerta: list[str] = Field(default_factory=list)    # risco de esfriar, insatisfação, expectativa irreal...
    como_abordar: list[str] = Field(default_factory=list)     # 3–5 recomendações concretas para o corretor
    resumo_perfil: str = ""                    # 1–2 frases


class Cliente(BaseModel):
    """A PESSOA. Uma por telefone/e-mail, a mesma no Telegram e na web.
    O Lead é a oportunidade dela — um cliente pode ter várias ao longo do tempo."""
    id: str
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    criado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    atualizado_em: datetime | None = None


class Lead(BaseModel):
    """Uma OPORTUNIDADE: uma intenção, um cartão, um ciclo de atendimento."""
    id: str
    cliente_id: str | None = None
    nome: str | None = None
    telefone: str | None = None
    email: str | None = None
    estagio: Estagio = Estagio.NOVO
    temperatura: Temperatura = Temperatura.FRIO
    score: int = 0
    cartao: CartaoQualificacao = Field(default_factory=CartaoQualificacao)
    corretor_id: str | None = None
    resumo: str | None = None
    analise: AnaliseLead | None = None
    analisado_em: datetime | None = None
    analise_solicitada_em: datetime | None = None
    followups_enviados: int = 0
    criado_em: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    ultima_mensagem_em: datetime | None = None
    aceita_reativacao: bool = True             # opt-out de aviso sobre imóvel novo
    reativado_em: datetime | None = None       # último aviso de imóvel novo (cadência da reativação)
    encerrado_em: datetime | None = None       # oportunidade fechada; a conversa segue na sucessora
    sucessora_id: str | None = None            # a intenção mudou e abrimos outra oportunidade

    @field_validator("nome", "telefone", "email", mode="before")
    @classmethod
    def _identidade_sem_veneno(cls, v):
        return _limpar_identidade(v, 120)

    def ativa(self) -> bool:
        return self.encerrado_em is None
