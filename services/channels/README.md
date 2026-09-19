# channels — adaptadores de canal (ADR-0003)

Cada subpasta é um canal. Contrato obrigatório de cada adaptador:

```python
def parse_inbound(evento_bruto) -> list[MensagemNormalizada]
def render(resposta: RespostaAgente) -> payload do provedor
```

Fluxo: provedor → entrada → tópico Redis `inbound` → agent → tópico `outbound-<canal>` → saída →
provedor. Entrada e saída são **workers** (`local_worker()`) do `local/docker-compose.yml`, não
funções hospedadas.

- `telegram/` — canal externo. Entrada por long polling (`getUpdates`), sem webhook e sem URL
  pública (ADR-0007); saída pela Bot API. Pacote `canal_telegram`, workers `telegram-in` e
  `telegram-out`.
- `local/` — canal web: um processo FastAPI com o WebSocket `/ws` (widget do site com `papel=lead`,
  painel com `papel=dashboard`) e o worker que consome `outbound-web`.

Havia aqui um canal `whatsapp/`, pela Cloud API da Meta; foi removido, porque o webhook exige URL
pública e conta de negócio verificada.

Um canal nunca tem nome de pacote genérico (`src`), que colidiria com o dos outros. Canais não
chamam o LLM, não leem o cartão do lead e não têm regra de negócio.
