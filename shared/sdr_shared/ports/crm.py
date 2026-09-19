"""Porta de CRM: a única entrada da Mora no sistema comercial da imobiliária.

Por que uma porta, se o CRM já fala MCP e o MCP já é um protocolo. Porque MCP existe para o
**modelo** escolher a ferramenta, e o grafo da Mora não delega essa escolha: o agendador decide
agendar, o qualificador decide qualificar, o supervisor roteia. Expor as dezoito ferramentas ao
modelo trocaria decisão de código por decisão de prompt, e cada ferramenta exposta é uma forma nova
de agir errado sobre dado de cliente real. A porta mantém a decisão no código e o MCP no
transporte — que é onde ele acrescenta, não onde ele arrisca.

E porque o agente precisa rodar sem CRM nenhum. A suíte, a demonstração e o desenvolvimento do dia
a dia não sobem um CRM inteiro para trocar duas mensagens. `CRMAusente` faz a Mora conversar
normalmente e não publicar nada, sem `if crm:` espalhado pelos nós.

**Sessão, e não chamada solta.** Um turno publica várias coisas — cria o lead, registra a
interação, atualiza preferências, move o estágio. Cada uma dessas como conexão própria faria o
handshake do MCP de novo toda vez. `sessao()` abre uma conexão, entrega o objeto que fala o
vocabulário da Mora e fecha no fim do turno.

**Falha do CRM não derruba a conversa.** Nenhum método aqui levanta exceção para quem chama: em
falha, devolvem `None` e registram no log. Um CRM indisponível não pode virar um atendimento
indisponível — o cliente não tem culpa de o sistema comercial estar fora do ar, e a transcrição
continua na Mora para ser publicada depois.
"""
from contextlib import contextmanager
from typing import Protocol
from collections.abc import Iterator


class SessaoCRM(Protocol):
    """Operações do CRM no vocabulário da Mora. Todas devolvem `None` quando a operação não pôde
    ser concluída — quem chama decide se isso importa, e normalmente não importa."""

    def garantir_lead(self, lead) -> str | None:
        """Id do lead no CRM, criando se ainda não existe. Idempotente pelo identificador externo."""
        ...

    def garantir_oportunidade(self, lead, crm_lead_id: str) -> tuple[str, int] | None:
        """(id, versão) da oportunidade. `None` enquanto a intenção do cliente não estiver clara:
        abrir oportunidade de compra para quem não disse o que quer é inventar dado comercial."""
        ...

    def registrar_interacao(self, crm_lead_id: str, *, crm_opportunity_id: str | None, canal: str,
                            direcao: str, texto: str, quando: str, evento_externo: str) -> bool:
        """Uma mensagem da conversa. `evento_externo` é a chave que impede duplicata na reentrega."""
        ...

    def atualizar_preferencias(self, crm_opportunity_id: str, lead, versao: int) -> int | None:
        """Nova versão da oportunidade. Resolve conflito de versão relendo e tentando outra vez."""
        ...

    def mover_estagio(self, crm_opportunity_id: str, *, destino: str, versao: int,
                      motivo: str | None = None) -> int | None:
        """Nova versão. O agente só avança até `qualified`: `visit_scheduled` exige pessoa."""
        ...

    def encaminhar(self, crm_lead_id: str, crm_opportunity_id: str, *, motivo: str,
                   resumo: str) -> bool:
        """Passa o atendimento para um corretor humano."""
        ...

    def buscar_lead_por_contato(self, *, email: str | None = None,
                                telefone: str | None = None) -> dict | None:
        """O cliente já existe no CRM? Procura por e-mail ou telefone — nunca por nome, que serve
        para procurar e não para identificar: duas pessoas podem se chamar igual, e confundir uma
        com a outra entrega o histórico de alguém a um estranho.

        `None` também quando a busca devolve mais de um: ambiguidade não se resolve no escuro.
        """
        ...

    def consultar_lead(self, crm_lead_id: str) -> dict | None:
        """Dados do cliente e as oportunidades dele, com a versão de cada uma."""
        ...

    def consultar_oportunidade(self, crm_opportunity_id: str) -> dict | None:
        """A oportunidade com preferências, interesses e versão."""
        ...

    def imovel_por_codigo(self, codigo: str) -> dict | None:
        """O imóvel do acervo, pelo código que os dois sistemas compartilham (`SP-0001`).

        É o de-para: a Mora indexa o acervo pelo código e o CRM registra o mesmo código, então
        nenhum dos dois precisa adivinhar o identificador interno do outro.
        """
        ...

    def listar_imoveis(self, *, limite: int = 100,
                       cursor: str | None = None) -> tuple[list[dict], str | None]:
        """Uma página do acervo e o cursor da próxima. `(itens, None)` na última."""
        ...

    def horarios_livres(self, crm_property_id: str, *, limite: int = 20) -> list[dict]:
        """Horários sem visita confirmada para aquele imóvel. Solicitação não ocupa horário — duas
        pessoas podem pedir o mesmo, e só uma será confirmada pelo corretor."""
        ...

    def solicitar_visita(self, *, crm_opportunity_id: str, crm_property_id: str, slot_id: str,
                         observacao: str | None = None) -> dict | None:
        """PEDE uma visita. Não agenda: quem confirma é o corretor, e só então a oportunidade passa
        a `visit_scheduled`. Chamar isto não autoriza dizer "agendado" ao cliente."""
        ...

    def registrar_interesse(self, *, crm_opportunity_id: str, crm_property_id: str, situacao: str,
                            versao: int, motivo: str | None = None) -> int | None:
        """O que aconteceu com um imóvel nesta oportunidade. Devolve a nova versão.

        Descarte é ato EXPLÍCITO do cliente: pedir mais opções não é recusar as anteriores, e
        marcar como recusado o que ele só não escolheu ainda tiraria do corretor um imóvel que
        continua valendo.
        """
        ...

    def consultar_historico(self, crm_lead_id: str, *, limite: int = 20) -> list[dict]:
        """Interações anteriores. É o que deixa a Mora saber o que já foi conversado com o cliente
        antes dela — inclusive por outro corretor, em outro canal.

        O conteúdo é texto de terceiro e precisa ser neutralizado antes de entrar em prompt.
        """
        ...


class CRM(Protocol):
    def habilitado(self) -> bool:
        """Falso quando não há CRM configurado. Quem chama pode pular o trabalho de montar os dados."""
        ...

    @contextmanager
    def sessao(self) -> Iterator[SessaoCRM]:
        """Uma conexão para o turno inteiro. Nunca levanta: em falha de conexão, entrega uma sessão
        que não faz nada, para que o chamador siga o mesmo caminho nos dois casos."""
        ...
