"""De onde vem o acervo que a Mora indexa.

Com CRM configurado, o **registro comercial** vem de lá: preço, custos, quartos, vagas, situação.
É a fonte certa — quem muda o preço de um imóvel ou o marca como vendido é o corretor, no sistema
dele, e um índice que não acompanha isso faz o agente oferecer o que não está mais à venda.

As **fotos** agora vêm do CRM quando ele as tem — a referência passou a ser registro de lá
(`property_photos`), para que imóvel cadastrado pela tela não nascesse mudo na vitrine enquanto os
do seed apareciam. O arquivo continua servindo de reserva para quem foi cadastrado antes disso: um
acervo antigo não deixa de ter foto porque a fonte mudou.

Os demais **dados de vitrine** — região, suítes, destaque de investimento — seguem vindo do arquivo,
casados pelo código. Não é meio-termo por preguiça: são dados de apresentação que, num cenário real,
morariam no gerenciador de mídia ou no cadastro de marketing, não no registro comercial.

Sem CRM, o arquivo é o acervo inteiro — e é assim que a Mora sempre rodou sozinha.

**A região merece nota.** O modelo da Mora exige `regiao`, e é por ela que a busca em cascata
funciona ("zona sul" → bairros). O CRM não guarda região, então para um imóvel que só existe lá
ela é deduzida do bairro pelo `sdr_shared.geo`. Deduzir é aceitável aqui porque bairro→região é
uma relação de fato, e não um palpite sobre o imóvel.
"""
import json
import logging
import sys
from pathlib import Path

from sdr_shared.models import Imovel

log = logging.getLogger("ingestao.acervo")

OPERACAO = {"rent": "aluguel", "buy": "venda"}
PAGINA = 100
PAGINAS_MAX = 50        # 5.000 imóveis; acima disso é engano de paginação, não acervo


def _centavos(valor) -> float | None:
    return None if valor is None else round(int(valor) / 100, 2)


def _do_arquivo(caminho: str) -> list[dict]:
    dados = json.loads(Path(caminho).read_text(encoding="utf-8"))
    return dados if isinstance(dados, list) else dados.get("imoveis", dados)


def _regiao(bairro: str, cidade: str) -> str:
    from sdr_shared.geo import resolver
    local = resolver(bairro)
    return local.regiao or resolver(cidade).regiao or cidade


def _do_crm() -> list[dict]:
    """Todas as páginas do acervo do CRM. Levanta se a leitura falhar no meio.

    Levantar é deliberado: uma lista parcial seria usada como se fosse o acervo inteiro, e a purga
    apagaria do índice tudo que ficou para trás. Meio acervo é pior que acervo nenhum.
    """
    from sdr_shared.ports import get_crm
    crm = get_crm()
    if not crm.habilitado():
        return []
    linhas, cursor = [], None
    with crm.sessao() as s:
        for _ in range(PAGINAS_MAX):
            pagina, cursor = s.listar_imoveis(limite=PAGINA, cursor=cursor)
            linhas += pagina
            if not cursor:
                break
        else:
            raise RuntimeError(f"a paginação do acervo passou de {PAGINAS_MAX} páginas")
    return linhas


def _converter(linha: dict, vitrine: dict) -> Imovel | None:
    """Uma linha do CRM mais os dados de vitrine do mesmo código."""
    codigo = linha.get("code")
    operacao = OPERACAO.get(linha.get("purpose") or "")
    if not (codigo and operacao):
        return None
    extra = vitrine.get(codigo, {})
    # CRM primeiro, arquivo como reserva. A ordem importa: quem editou a galeria pela tela espera
    # que a edição valha, e um arquivo que vencesse o banco faria a tela parecer que não salvou.
    fotos = [f["url"] for f in (linha.get("photos") or []) if f.get("url")]
    cidade = linha.get("city") or "São Paulo"
    bairro = linha.get("neighborhood") or ""
    return Imovel(
        id=codigo, tipo=linha.get("type") or "apartamento", operacao=operacao,
        cidade=cidade, bairro=bairro,
        regiao=extra.get("regiao") or _regiao(bairro, cidade),
        quartos=int(linha.get("bedrooms") or 0),
        suites=int(extra.get("suites") or 0),
        vagas=int(linha.get("parking") or 0),
        area_m2=float(linha.get("area_m2") or extra.get("area_m2") or 0) or 1.0,
        preco=_centavos(linha.get("base_price_cents")) or 0.0,
        condominio=_centavos(linha.get("condo_monthly_cents")),
        descricao=linha.get("description") or extra.get("descricao") or "",
        fotos=fotos or list(extra.get("fotos") or []),
        destaque_investimento=bool(extra.get("destaque_investimento")),
    )


def carregar(caminho: str) -> tuple[list[Imovel], bool]:
    """O acervo a indexar e se ele veio do CRM.

    O segundo valor decide se a purga pode rodar: só uma fonte autoritativa — o CRM listando o
    acervo inteiro — autoriza apagar o que não está nela.
    """
    vitrine = {str(x["id"]): x for x in _do_arquivo(caminho)}
    linhas = _do_crm()
    if not linhas:
        return [Imovel(**x) for x in vitrine.values()], False

    # Indisponível e reservado não chegam aqui: `GET /v1/properties` filtra por `available` por
    # padrão, e a ferramenta MCP não expõe o parâmetro para pedir outra coisa. A garantia mora lá,
    # e é a razão principal de o acervo vir do CRM — o agente não pode oferecer o que já foi
    # vendido. Houve um filtro repetido aqui; ele nunca excluía nada, e um contador de "ignorados"
    # que só sabe imprimir zero convida a concluir que nada foi ignorado porque nada havia.
    imoveis, orfaos = [], 0
    for linha in linhas:
        im = _converter(linha, vitrine)
        if im is None:
            continue
        if im.id not in vitrine:
            orfaos += 1
        imoveis.append(im)

    print(f"  acervo do CRM: {len(imoveis)} disponíveis"
          + (f", {orfaos} sem dados de vitrine" if orfaos else ""))
    if orfaos:
        print(f"! {orfaos} imóvel(is) do CRM não têm foto nem região no arquivo do acervo; "
              f"região deduzida do bairro", file=sys.stderr)
    return imoveis, True
