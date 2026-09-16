from aws_cdk import Stack, Duration, aws_sqs as sqs, aws_events as events
from constructs import Construct


class MessagingStack(Stack):
    """Filas FIFO por lead (ordem garantida) + barramento de eventos de domínio."""
    def __init__(self, scope: Construct, id: str, **kw):
        super().__init__(scope, id, **kw)
        dlq = sqs.Queue(self, "Dlq", queue_name="sdr-dlq.fifo", fifo=True)
        self.inbound = sqs.Queue(self, "Inbound", queue_name="sdr-inbound.fifo", fifo=True,
                                 content_based_deduplication=True, visibility_timeout=Duration.seconds(180),
                                 dead_letter_queue=sqs.DeadLetterQueue(max_receive_count=3, queue=dlq))
        # Uma fila de saída por canal. `telegram` é o canal ativo (ADR-0007); `whatsapp` continua
        # porque o adaptador existe e o perfil local ainda serve o webhook — a fila custa nada parada.
        self.outbound = {c: sqs.Queue(self, f"Outbound{c.title()}", queue_name=f"sdr-outbound-{c}.fifo", fifo=True,
                                      content_based_deduplication=True) for c in ("telegram", "whatsapp", "web")}
        self.resumir = sqs.Queue(self, "Resumir", queue_name="sdr-resumir.fifo", fifo=True, content_based_deduplication=True)
        # Imóvel novo → reativador. FIFO com dedupe por conteúdo: reprocessar a mesma ingestão duas
        # vezes em sequência não vira dois avisos para as mesmas pessoas.
        self.imovel_novo = sqs.Queue(self, "ImovelNovo", queue_name="sdr-imovel-novo.fifo", fifo=True,
                                     content_based_deduplication=True, visibility_timeout=Duration.seconds(300))
        self.events = sqs.Queue(self, "Events", queue_name="sdr-events.fifo", fifo=True, content_based_deduplication=True)
        self.bus = events.EventBus(self, "Bus", event_bus_name="sdr-events")
