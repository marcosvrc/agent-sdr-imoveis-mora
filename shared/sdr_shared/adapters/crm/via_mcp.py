"""Adaptador da porta de CRM falando MCP sobre HTTP.

O servidor MCP do CRM é um serviço da rede, não um processo filho do agente. Essa escolha é sobre
honestidade de topologia: no mundo real a imobiliária publica o CRM dela e a Mora é um sistema
separado que se conecta. Subir o CRM como subprocesso funcionaria na demonstração e mentiria sobre
o desenho.

O cliente MCP é assíncrono e o grafo da Mora é síncrono. A ponte é um portal do anyio — um laço de
eventos numa thread de fundo — aberto uma vez por `sessao()`. Fazer isso por chamada refaria o
handshake do MCP a cada operação; um turno publica meia dúzia de coisas.

Nada aqui levanta exceção para cima. Erro de rede, CRM fora do ar, ferramenta recusando a operação:
tudo vira `None` e uma linha de log. A regra do pacote continua valendo — um CRM indisponível não
pode virar um atendimento indisponível.
"""
import hashlib
import logging
import os
from contextlib import ExitStack, contextmanager
from collections.abc import Iterator

from ...crm import traducao

log = logging.getLogger("crm.mcp")

TIMEOUT = 10.0

# Recusas que são o CRM funcionando, e não falhando: com o atendimento em mãos humanas ou o contato
# bloqueado, é ESPERADO que a escrita não passe. Vão a debug para não poluir o log de erro.
ESPERADOS = frozenset({"HUMAN_IN_CONTROL", "CONTACT_BLOCKED", "FORBIDDEN",
                       "QUALIFICATION_INCOMPLETE", "INVALID_TRANSITION"})


def _op(lead_id: str, acao: str, marca: str = "") -> str:
    """Identificador ESTÁVEL da ação lógica.

    Deriva do lead e do fato, nunca do relógio nem de um aleatório: é isso que faz a repetição da
    mesma publicação, num turno seguinte ou depois de um timeout, encontrar o registro já gravado
    em vez de criar um segundo.
    """
    digest = hashlib.sha256(f"{lead_id}:{acao}:{marca}".encode()).hexdigest()[:24]
    return f"mora-{acao}-{digest}"


def _versao(dados: dict | None) -> int | None:
    """A versão da oportunidade, sob qualquer um dos dois nomes que o CRM usa.

    `criar_oportunidade` e `consultar_oportunidade` devolvem a linha, onde o campo é `version`.
    `atualizar_preferencias` e `mover_oportunidade` devolvem o recurso alterado MAIS a nova versão
    da oportunidade num campo à parte, `opportunity_version` — porque o recurso alterado ali é a
    preferência ou a transição, e o `version` deles seria outra coisa. Ler só `version` traria a
    versão do objeto errado, ou nenhuma, e o próximo `If-Match` iria com um número velho: o sintoma
    seria um 412 inexplicável no turno seguinte, longe daqui.
    """
    if not dados:
        return None
    for campo in ("opportunity_version", "version"):
        if campo in dados:
            return int(dados[campo])
    return None


class _Sessao:
    """Uma conexão MCP aberta, falando o vocabulário da Mora."""

    def __init__(self, chamar) -> None:
        self._chamar = chamar

    # ------------------------------------------------------------------ infraestrutura

    def _ferramenta(self, nome: str, argumentos: dict) -> dict | None:
        """Chama a ferramenta e devolve `data`, ou `None` se não deu certo."""
        try:
            resultado = self._chamar(nome, argumentos)
        except Exception:
            log.warning("CRM inacessível ao chamar %s — a conversa segue", nome, exc_info=True)
            return None
        # O modelo do CLIENTE nomeia os campos em snake_case (`structured_content`), enquanto o
        # tipo do servidor usa o nome do protocolo (`structuredContent`). Ler só um dos dois deixa
        # o envelope sempre vazio e TODA chamada vira "recusada", sem mensagem — que foi
        # exatamente o sintoma. Aceitar os dois nomes tira o acerto da dependência da versão do SDK.
        corpo = (getattr(resultado, "structured_content", None)
                 or getattr(resultado, "structuredContent", None) or {})
        if corpo.get("ok"):
            dados = corpo.get("data")
            return dados if isinstance(dados, dict) else {"data": dados}
        erro = corpo.get("error") or {}
        codigo = erro.get("code", "DESCONHECIDO")
        nivel = log.debug if codigo in ESPERADOS else log.warning
        nivel("CRM recusou %s: %s %s", nome, codigo, erro.get("message", ""))
        return None

    # ------------------------------------------------------------------ operações

    def garantir_lead(self, lead) -> str | None:
        dados = traducao.identificadores(lead)
        r = self._ferramenta("criar_lead", {
            **dados, "operation_id": _op(lead.id, "lead", dados.get("external_contact_id", ""))})
        return (r or {}).get("id")

    def garantir_oportunidade(self, lead, crm_lead_id: str) -> tuple[str, int] | None:
        proposito = traducao.proposito(lead)
        if not proposito:
            return None            # intenção ainda não clara; não se inventa oportunidade
        r = self._ferramenta("criar_oportunidade", {
            "lead_id": crm_lead_id, "purpose": proposito,
            "operation_id": _op(lead.id, "oportunidade", proposito)})
        if not r or "id" not in r:
            return None
        return r["id"], _versao(r) or 1

    def registrar_interacao(self, crm_lead_id: str, *, crm_opportunity_id: str | None, canal: str,
                            direcao: str, texto: str, quando: str, evento_externo: str) -> bool:
        return self._ferramenta("registrar_interacao", {
            "lead_id": crm_lead_id, "opportunity_id": crm_opportunity_id, "channel": canal,
            "direction": direcao, "summary": texto[:4000], "occurred_at": quando,
            "external_event_id": evento_externo,
            "operation_id": _op(crm_lead_id, f"interacao-{direcao}", evento_externo)}) is not None

    def atualizar_preferencias(self, crm_opportunity_id: str, lead, versao: int) -> int | None:
        corpo = traducao.preferencias(lead)
        marca = hashlib.sha256(repr(sorted(corpo.items())).encode()).hexdigest()[:16]
        argumentos = {"opportunity_id": crm_opportunity_id, **corpo,
                      "operation_id": _op(lead.id, "prefs", marca)}
        r = self._ferramenta("atualizar_preferencias", {**argumentos, "expected_version": versao})
        if r is None:
            # Conflito de versão é o caso normal de duas escritas no mesmo turno: relê e repete uma
            # vez. Repetir sem reler entraria em laço contra a mesma versão velha.
            atual = self._ferramenta("consultar_oportunidade", {"opportunity_id": crm_opportunity_id})
            versao_atual = _versao(atual)
            if versao_atual is None:
                return None
            r = self._ferramenta("atualizar_preferencias",
                                 {**argumentos, "expected_version": versao_atual})
        return _versao(r)

    def mover_estagio(self, crm_opportunity_id: str, *, destino: str, versao: int,
                      motivo: str | None = None) -> int | None:
        r = self._ferramenta("mover_oportunidade", {
            "opportunity_id": crm_opportunity_id, "target_stage": destino,
            "expected_version": versao, "reason": motivo,
            "operation_id": _op(crm_opportunity_id, f"estagio-{destino}")})
        return _versao(r)

    def encaminhar(self, crm_lead_id: str, crm_opportunity_id: str, *, motivo: str,
                   resumo: str, destinatario: str | None = None) -> bool:
        corpo = {"lead_id": crm_lead_id, "opportunity_id": crm_opportunity_id,
                 "reason": motivo, "summary": resumo,
                 "operation_id": _op(crm_lead_id, "handoff")}
        if destinatario:
            corpo["assignee_id"] = destinatario
        return self._ferramenta("encaminhar_para_corretor", corpo) is not None

    def buscar_lead_por_contato(self, *, email: str | None = None,
                                telefone: str | None = None) -> dict | None:
        if not (email or telefone):
            return None
        r = self._ferramenta("buscar_leads", {"email": email, "phone": telefone, "limit": 2})
        achados = (r or {}).get("items") or []
        if len(achados) != 1:
            # Zero é o caso comum: cliente novo. Mais de um é ambiguidade real — dois cadastros com
            # o mesmo telefone —, e escolher um no escuro entregaria o histórico de uma pessoa a
            # outra. Nos dois casos a Mora segue perguntando do zero, que é seguro.
            if len(achados) > 1:
                log.info("mais de um cliente no CRM com o mesmo contato; seguindo sem reconhecer")
            return None
        return achados[0]

    def consultar_lead(self, crm_lead_id: str) -> dict | None:
        return self._ferramenta("consultar_lead", {"lead_id": crm_lead_id})

    def consultar_oportunidade(self, crm_opportunity_id: str) -> dict | None:
        return self._ferramenta("consultar_oportunidade", {"opportunity_id": crm_opportunity_id})

    def imovel_por_codigo(self, codigo: str) -> dict | None:
        r = self._ferramenta("buscar_imoveis", {"code": codigo, "limit": 2})
        itens = (r or {}).get("items") or []
        # `code` é único no CRM; mais de um resultado seria o filtro tendo sido ignorado, e aí o
        # primeiro item é um imóvel qualquer. Melhor não resolver do que resolver errado: um pedido
        # de visita no imóvel errado é pior que nenhum.
        if len(itens) != 1:
            if itens:
                log.warning("busca por código %s devolveu %d imóveis; não resolvi", codigo, len(itens))
            return None
        return itens[0]

    def listar_imoveis(self, *, limite: int = 100,
                       cursor: str | None = None) -> tuple[list[dict], str | None]:
        r = self._ferramenta("buscar_imoveis", {"limit": limite, "cursor": cursor})
        if r is None:
            # Falha no meio da paginação não pode virar "acabou": quem consome usaria a lista
            # parcial como se fosse o acervo inteiro e apagaria o resto do índice.
            raise RuntimeError("o CRM não respondeu durante a listagem do acervo")
        itens = r.get("items")
        return (itens if isinstance(itens, list) else []), r.get("next_cursor")

    def horarios_livres(self, crm_property_id: str, *, limite: int = 20) -> list[dict]:
        r = self._ferramenta("consultar_horarios", {"property_id": crm_property_id,
                                                    "limit": limite})
        itens = (r or {}).get("items")
        return itens if isinstance(itens, list) else []

    def solicitar_visita(self, *, crm_opportunity_id: str, crm_property_id: str, slot_id: str,
                         observacao: str | None = None) -> dict | None:
        return self._ferramenta("solicitar_visita", {
            "opportunity_id": crm_opportunity_id, "property_id": crm_property_id,
            "slot_id": slot_id, "notes": observacao,
            "operation_id": _op(crm_opportunity_id, "visita", slot_id)})

    def registrar_interesse(self, *, crm_opportunity_id: str, crm_property_id: str, situacao: str,
                            versao: int, motivo: str | None = None) -> int | None:
        r = self._ferramenta("registrar_interesse", {
            "opportunity_id": crm_opportunity_id, "property_id": crm_property_id,
            "status": situacao, "notes": motivo, "expected_version": versao,
            "operation_id": _op(crm_opportunity_id, f"interesse-{situacao}", crm_property_id)})
        return _versao(r)

    def consultar_historico(self, crm_lead_id: str, *, limite: int = 20) -> list[dict]:
        r = self._ferramenta("consultar_historico", {"lead_id": crm_lead_id, "limit": limite})
        if not r:
            return []
        itens = r.get("items", r.get("data"))
        return itens if isinstance(itens, list) else []


class _Inerte:
    """Sessão que aceita tudo e não faz nada. É o que `sessao()` entrega quando a conexão falha, para
    que o chamador tenha UM caminho em vez de dois."""

    def garantir_lead(self, lead): return None
    def garantir_oportunidade(self, lead, crm_lead_id): return None
    def registrar_interacao(self, crm_lead_id, **k): return False
    def atualizar_preferencias(self, crm_opportunity_id, lead, versao): return None
    def mover_estagio(self, crm_opportunity_id, **k): return None
    def encaminhar(self, crm_lead_id, crm_opportunity_id, **k): return False
    def buscar_lead_por_contato(self, **k): return None
    def consultar_lead(self, crm_lead_id): return None
    def consultar_oportunidade(self, crm_opportunity_id): return None
    def imovel_por_codigo(self, codigo): return None
    def listar_imoveis(self, **k): return [], None
    def horarios_livres(self, crm_property_id, **k): return []
    def solicitar_visita(self, **k): return None
    def registrar_interesse(self, **k): return None
    def consultar_historico(self, crm_lead_id, **k): return []


class CRMviaMCP:
    def __init__(self, url: str | None = None, token: str | None = None) -> None:
        self.url = (url if url is not None else os.environ.get("SDR_CRM_URL", "")).strip()
        self.token = (token if token is not None else os.environ.get("SDR_CRM_TOKEN", "")).strip()

    def habilitado(self) -> bool:
        """URL **e** token. Sem token, o servidor recusa — e descobrir isso no meio da conversa é
        pior do que saber agora que o CRM não está configurado."""
        return bool(self.url and self.token)

    @contextmanager
    def sessao(self) -> Iterator:
        if not self.habilitado():
            yield _Inerte()
            return
        import httpx
        from anyio.from_thread import start_blocking_portal
        from mcp.client.client import Client
        from mcp.client.streamable_http import streamable_http_client

        # A conexão é montada numa pilha própria, FORA do `yield`. Envolver o `yield` num `except`
        # faria uma exceção do chamador cair aqui e o gerador render duas vezes — o
        # `RuntimeError: generator didn't stop after throw()`, que apareceria como um erro do CRM
        # numa falha que não tem nada a ver com ele.
        pilha = ExitStack()
        try:
            portal = pilha.enter_context(start_blocking_portal())
            http = httpx.AsyncClient(headers={"Authorization": f"Bearer {self.token}"},
                                     timeout=TIMEOUT)
            cliente = pilha.enter_context(portal.wrap_async_context_manager(
                Client(streamable_http_client(self.url, http_client=http))))
        except Exception:
            pilha.close()
            log.warning("não foi possível abrir sessão MCP com o CRM (%s) — a conversa segue",
                        self.url, exc_info=True)
            yield _Inerte()
            return

        try:
            def chamar(nome: str, argumentos: dict):
                # `None` não é "apague este campo" para o CRM: é argumento ausente. Mandar explícito
                # faria o validador recusar a chamada inteira por causa de um campo opcional vazio.
                limpos = {k: v for k, v in argumentos.items() if v is not None}
                return portal.call(cliente.call_tool, nome, limpos)
            yield _Sessao(chamar)
        finally:
            pilha.close()
