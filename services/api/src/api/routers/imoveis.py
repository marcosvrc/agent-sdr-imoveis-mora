"""Imóveis: leitura pública (site, chat) e gestão de fotos pelo painel (autenticado).
Fotos: o painel envia a imagem em base64 (já reduzida no navegador); gravamos em `fotos_dir/<imovel>/<uuid>.jpg`
e guardamos o caminho relativo `/fotos/<imovel>/<arquivo>` — a API devolve sempre a URL absoluta."""
import base64
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sdr_shared.config import get_settings
from sdr_shared.db import ImovelRepository
from sdr_shared.geo import BAIRROS
from sdr_shared.models import Imovel
from ..auth import corretor_atual

router = APIRouter()
MAX_FOTOS, MAX_BYTES = 12, 1_500_000


class ImovelPublico(Imovel):
    """Resposta pública: mesmo imóvel + pontos de referência do bairro (dado que já existe em
    `sdr_shared.geo` para o agente entender "perto da Faria Lima" — o site só expõe o que já existia)."""
    pontos_referencia: list[str] = Field(default_factory=list)


def _publico(im: Imovel, request: Request) -> ImovelPublico:
    dados = im.model_dump()
    dados["fotos"] = im.fotos_absolutas(str(request.base_url))
    dados["pontos_referencia"] = BAIRROS.get(im.bairro, {}).get("refs", [])
    return ImovelPublico(**dados)


@router.get("", response_model=list[ImovelPublico])
def listar(request: Request, operacao: str | None = None, regiao: str | None = None, preco_max: float | None = None,
           quartos: int | None = None, limite: int = Query(60, le=200)):
    return [_publico(i, request) for i in ImovelRepository().listar_publico(operacao=operacao, regiao=regiao, preco_max=preco_max, quartos=quartos, limite=limite)]


class Busca(BaseModel):
    """Resposta da busca do site. Tem `total` porque a lista sozinha não diz quantos existem — e sem
    isso a página é obrigada a baixar o catálogo inteiro para contar."""
    itens: list[ImovelPublico]
    total: int
    bairros: list[dict]           # [{bairro, n}] para a lista de bairros da tela
    limite: int
    offset: int


@router.get("/busca", response_model=Busca)
def busca(request: Request,
          operacao: str | None = None, regiao: str | None = None, bairro: str | None = None,
          tipo: str | None = None, preco_min: float | None = Query(None, ge=0),
          preco_max: float | None = Query(None, ge=0), quartos: int | None = Query(None, ge=0, le=10),
          suites: int | None = Query(None, ge=0, le=10), vagas: int | None = Query(None, ge=0, le=10),
          area_min: float | None = Query(None, ge=0), texto: str | None = Query(None, max_length=80),
          ordenar: str = Query("relevancia"), limite: int = Query(24, ge=1, le=60), offset: int = Query(0, ge=0)):
    """Catálogo paginado com filtros — a rota que a vitrine usa.

    Fica separada de `GET /imoveis` (que continua igual, sem paginação, e é o que o chat e os testes
    antigos consomem) para não quebrar contrato de ninguém ao introduzir a forma nova."""
    if ordenar not in ImovelRepository.ORDENACOES:
        raise HTTPException(422, f"ordenação inválida: {ordenar}")
    r = ImovelRepository().buscar_publico(
        {"operacao": operacao, "regiao": regiao, "bairro": bairro, "tipo": tipo, "preco_min": preco_min,
         "preco_max": preco_max, "quartos": quartos, "suites": suites, "vagas": vagas,
         "area_min": area_min, "texto": texto},
        ordenar=ordenar, limite=limite, offset=offset)
    return Busca(itens=[_publico(i, request) for i in r["itens"]], total=r["total"],
                 bairros=r["bairros"], limite=limite, offset=offset)


@router.get("/{imovel_id}", response_model=ImovelPublico)
def detalhe(imovel_id: str, request: Request):
    if im := ImovelRepository().get(imovel_id):
        return _publico(im, request)
    raise HTTPException(404, "imóvel não encontrado")


class FotoIn(BaseModel):
    imagem: str      # data:image/jpeg;base64,...


def _dir(imovel_id: str) -> Path:
    d = Path(get_settings().fotos_dir) / imovel_id
    d.mkdir(parents=True, exist_ok=True)
    return d


@router.post("/{imovel_id}/fotos", response_model=Imovel, status_code=201, dependencies=[Depends(corretor_atual)])
def enviar_foto(imovel_id: str, body: FotoIn, request: Request):
    im = ImovelRepository().get(imovel_id)
    if not im:
        raise HTTPException(404, "imóvel não encontrado")
    if len(im.fotos) >= MAX_FOTOS:
        raise HTTPException(409, f"limite de {MAX_FOTOS} fotos por imóvel")
    m = re.match(r"^data:image/(jpeg|png|webp);base64,([A-Za-z0-9+/=]+)$", body.imagem)
    if not m:
        raise HTTPException(422, "imagem deve ser JPEG, PNG ou WebP em base64")
    # Tamanho conferido ANTES de decodificar: base64 rende 3 bytes a cada 4 caracteres, então o
    # texto já diz se a imagem passa do teto — decodificar para depois medir gastava a memória que
    # o teto existe para poupar.
    if len(m.group(2)) * 3 // 4 > MAX_BYTES:
        raise HTTPException(413, "imagem acima de 1,5 MB — reduza antes de enviar")
    dados = base64.b64decode(m.group(2))
    if len(dados) > MAX_BYTES:
        raise HTTPException(413, "imagem acima de 1,5 MB — reduza antes de enviar")
    ext = {"jpeg": "jpg", "png": "png", "webp": "webp"}[m.group(1)]
    nome = f"{uuid.uuid4().hex}.{ext}"
    (_dir(imovel_id) / nome).write_bytes(dados)
    fotos = [*im.fotos, f"/fotos/{imovel_id}/{nome}"]
    ImovelRepository().atualizar_fotos(imovel_id, fotos)
    return _publico(im.model_copy(update={"fotos": fotos}), request)


@router.delete("/{imovel_id}/fotos/{nome}", response_model=Imovel, dependencies=[Depends(corretor_atual)])
def remover_foto(imovel_id: str, nome: str, request: Request):
    im = ImovelRepository().get(imovel_id)
    if not im:
        raise HTTPException(404, "imóvel não encontrado")
    rel = f"/fotos/{imovel_id}/{nome}"
    if rel not in im.fotos:
        raise HTTPException(404, "foto não encontrada")
    if not re.fullmatch(r"[a-f0-9]{32}\.(jpg|png|webp)", nome):
        raise HTTPException(422, "nome inválido")
    (Path(get_settings().fotos_dir) / imovel_id / nome).unlink(missing_ok=True)
    fotos = [f for f in im.fotos if f != rel]
    ImovelRepository().atualizar_fotos(imovel_id, fotos)
    return _publico(im.model_copy(update={"fotos": fotos}), request)


class OrdemIn(BaseModel):
    fotos: list[str]     # caminhos/URLs na nova ordem (a primeira é a capa)


@router.put("/{imovel_id}/fotos", response_model=Imovel, dependencies=[Depends(corretor_atual)])
def reordenar_fotos(imovel_id: str, body: OrdemIn, request: Request):
    im = ImovelRepository().get(imovel_id)
    if not im:
        raise HTTPException(404, "imóvel não encontrado")
    base = str(request.base_url).rstrip("/")
    novas = [f[len(base):] if f.startswith(base + "/fotos/") else f for f in body.fotos]
    if sorted(novas) != sorted(im.fotos):
        raise HTTPException(422, "a lista deve conter exatamente as fotos atuais")
    ImovelRepository().atualizar_fotos(imovel_id, novas)
    return _publico(im.model_copy(update={"fotos": novas}), request)
