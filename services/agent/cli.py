"""Teste local do agente sem canal externo: `python cli.py` e converse no terminal."""
import uuid
from sdr_shared.messaging import MensagemNormalizada, Canal
from agent.handler import processar

lead_id = f"cli_{uuid.uuid4().hex[:6]}"
print(f"lead {lead_id} — digite 'sair' para encerrar")
while (txt := input("você> ")) != "sair":
    processar(MensagemNormalizada(lead_id=lead_id, canal=Canal.WEB, identificador_canal=lead_id, conteudo=txt))
