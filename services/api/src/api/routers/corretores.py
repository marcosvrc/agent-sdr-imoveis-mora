"""Cadastro de corretores (painel administrativo)."""
import re
import unicodedata
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sdr_shared.db import CorretorRepository, notificar
from sdr_shared.models import Corretor
from ..auth import corretor_atual

router = APIRouter(dependencies=[Depends(corretor_atual)])


class CorretorIn(BaseModel):
    nome: str = Field(min_length=2)
    email: str | None = None
    telefone: str | None = None
    regioes: list[str] = Field(default_factory=list)
    ativo: bool = True
    foto: str | None = None
    # `users.id` desta pessoa no CRM. Preenchido, o encaminhamento chega lá com destinatário em vez
    # de cair numa fila aberta — que é o que fazia os dois sistemas apontarem gente diferente.
    crm_user_id: str | None = None

    @field_validator("foto")
    @classmethod
    def _foto(cls, v: str | None) -> str | None:
        if not v:
            return None
        if not re.match(r"^data:image/(png|jpeg|webp);base64,[A-Za-z0-9+/=]+$", v) and not v.startswith("https://"):
            raise ValueError("foto deve ser uma imagem PNG/JPEG/WebP em base64 ou uma URL https")
        if len(v) > 300_000:
            raise ValueError("foto acima de 300 KB — reduza a imagem")
        return v


def _slug(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    return "cor_" + re.sub(r"[^a-z0-9]+", "-", base).strip("-")


@router.get("")
def listar():
    repo = CorretorRepository()
    carga = repo.carga()
    return [{**c.model_dump(mode="json"), "leads_handoff": 0, "visitas": 0, **carga.get(c.id, {})} for c in repo.listar()]


@router.post("", status_code=201)
def criar(body: CorretorIn):
    repo = CorretorRepository()
    cid = _slug(body.nome)
    if repo.get(cid):
        raise HTTPException(409, "já existe um corretor com esse nome")
    return repo.upsert(Corretor(id=cid, **body.model_dump()))


@router.put("/{corretor_id}")
def atualizar(corretor_id: str, body: CorretorIn):
    repo = CorretorRepository()
    if not repo.get(corretor_id):
        raise HTTPException(404)
    return repo.upsert(Corretor(id=corretor_id, **body.model_dump()))


@router.get("/{corretor_id}/carteira")
def carteira(corretor_id: str):
    """Quantos leads abertos e visitas futuras estão no nome deste corretor.

    A tela chama isto antes de desligar alguém, para perguntar para onde vai a carteira."""
    repo = CorretorRepository()
    if not repo.get(corretor_id):
        raise HTTPException(404)
    return repo.carteira(corretor_id)


@router.delete("/{corretor_id}", status_code=200)
def desativar(corretor_id: str,
              destino: str | None = Query(None, description=(
                  "Para onde vai a carteira: id de outro corretor, `equipe` (fila sem dono) ou "
                  "`auto` (distribui pelo roteamento por região e carga). Obrigatório quando a "
                  "carteira não está vazia.")),
              remover_cadastro: bool = Query(False, description=(
                  "Apaga o cadastro em vez de desativar. Só permitido com a carteira vazia — "
                  "existe para o cadastro criado por engano, não para desligar quem já atendeu."))):
    """Desliga o corretor: `ativo = false` e a carteira vai para quem você indicar.

    Não apaga o cadastro. Antes, o DELETE removia a linha e os leads ficavam apontando para um id
    inexistente — em handoff, atribuídos a ninguém e fora da lista de todo mundo. Desativar mantém
    o histórico (quem atendeu quem) e tira o corretor do roteamento de novos leads.
    """
    repo = CorretorRepository()
    corretor = repo.get(corretor_id)
    if not corretor:
        raise HTTPException(404)

    pendente = repo.carteira(corretor_id)
    tem_carteira = pendente["leads"] > 0 or pendente["visitas"] > 0

    if remover_cadastro:
        if tem_carteira:
            raise HTTPException(409, {"erro": "corretor com carteira aberta não pode ser apagado; "
                                              "desative e escolha um destino", **pendente})
        repo.remover(corretor_id)
        return {"acao": "removido", "corretor_id": corretor_id}

    # Sem destino e com carteira aberta, a resposta é 409 com os números: quem chamou precisa
    # DECIDIR. Escolher em silêncio (por exemplo, mandar tudo para a equipe) esconde a decisão.
    if tem_carteira and not destino:
        raise HTTPException(409, {"erro": "informe `destino` para a carteira deste corretor", **pendente})

    para = _resolver_destino(repo, destino, corretor)
    movido = repo.desativar(corretor_id, para)
    _avisar_transferencia(repo, corretor, para, movido)
    return {"acao": "desativado", "corretor_id": corretor_id,
            "destino": para or "equipe", "movido": {"leads": len(movido["leads"]), "visitas": movido["visitas"]}}


def _resolver_destino(repo: CorretorRepository, destino: str | None, saindo: Corretor) -> str | None:
    """`None`/`equipe` → fila da equipe. `auto` → roteamento por região e carga. Senão, um id."""
    if destino in (None, "", "equipe"):
        return None
    if destino == "auto":
        # A região do corretor que sai é a melhor pista de para onde a carteira dele deveria ir.
        escolhido = repo.escolher(saindo.regioes[0] if saindo.regioes else None)
        if escolhido and escolhido.id != saindo.id:
            return escolhido.id
        return None                       # sem outro ativo: fila da equipe, e não um beco sem saída
    alvo = repo.get(destino)
    if not alvo:
        raise HTTPException(422, f"corretor de destino inexistente: {destino}")
    if alvo.id == saindo.id:
        raise HTTPException(422, "o destino da carteira não pode ser o próprio corretor desativado")
    if not alvo.ativo:
        raise HTTPException(422, f"{alvo.nome} está inativo e não pode receber a carteira")
    return alvo.id


def _avisar_transferencia(repo: CorretorRepository, saindo: Corretor, para: str | None, movido: dict) -> None:
    """Um aviso por lead transferido. Lead que muda de dono em silêncio é lead esquecido —
    e a promessa que a Mora fez ao cliente ("um corretor entra em contato") continua de pé."""
    if not movido["leads"]:
        return
    quem = "a fila da equipe" if para is None else (repo.get(para).nome if repo.get(para) else "outro corretor")
    for lead_id in movido["leads"]:
        notificar(tipo="lead.transferido", corretor_id=para, lead_id=lead_id,
                  titulo=f"Lead transferido de {saindo.nome}",
                  detalhe=f"{saindo.nome} foi desativado; este atendimento passou para {quem}.",
                  chave=f"desativacao:{saindo.id}")
