"""Ponte da Mora para o CRM — em um sentido só.

A regra que governa este pacote inteiro, e que está registrada em `docs/decisions.md` (D-01):

    a Mora ESCREVE no CRM e LÊ do CRM, por MCP. Nada daqui toca o banco do CRM, e nada do CRM
    toca o banco da Mora.

O transporte é a porta `sdr_shared.ports.crm`, com o adaptador MCP sobre HTTP. Houve um cliente
REST próprio aqui; ele saiu quando a porta entrou. Dois caminhos para o mesmo sistema, com
autenticação e semântica de falha próprias, são dois lugares onde uma regra pode existir só de um
lado — que é exatamente o que este pacote foi escrito para evitar entre a Mora e o CRM.

O CRM é o registro **comercial** da imobiliária — oportunidade, preferências, interesses, visitas,
encaminhamento. A Mora continua dona do que é dela: a transcrição, o estado do grafo, os embeddings,
a cadência de follow-up e a reativação.

**Publicar nunca pode derrubar a conversa.** Se o CRM estiver fora do ar, o cliente não pode ficar
sem resposta por causa disso: toda função aqui engole a própria falha, registra no log e devolve o
controle. É a diferença entre um CRM indisponível e um atendimento indisponível.
"""
from .publicador import habilitado, publicar_encaminhamento, publicar_turno

__all__ = ["habilitado", "publicar_encaminhamento", "publicar_turno"]
