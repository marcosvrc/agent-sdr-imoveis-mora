import boto3


class SqsBroker:
    """Tópico = fila FIFO `sdr-<topic>.fifo`; key = MessageGroupId."""
    def __init__(self):
        self._sqs = boto3.client("sqs"); self._urls: dict[str, str] = {}

    def _url(self, topic: str) -> str:
        if topic not in self._urls:
            self._urls[topic] = self._sqs.get_queue_url(QueueName=f"sdr-{topic}.fifo")["QueueUrl"]
        return self._urls[topic]

    def publish(self, topic: str, body: str, key: str) -> None:
        self._sqs.send_message(QueueUrl=self._url(topic), MessageBody=body, MessageGroupId=key)

    def consume(self, topic, handler):
        raise NotImplementedError("Na AWS o consumo é feito pelo event source SQS → Lambda")
