# channels — adaptadores de canal (ADR-0003)

Cada subpasta é um canal. Contrato obrigatório de cada adaptador:

```python
def parse_inbound(evento_bruto) -> list[MensagemNormalizada]
def render(resposta: RespostaAgente) -> payload do provedor
```

Fluxo: provedor → `inbound` (Lambda) → SQS `sdr-inbound` → agent → SQS `sdr-outbound-<canal>` → `outbound` (Lambda) → provedor.
Cada canal tem um pacote com nome próprio (`canal_whatsapp`, `canal_web`) — nunca `src`, que colidiria entre eles.
Canais não chamam Bedrock, não leem o cartão do lead, não têm regra de negócio.
