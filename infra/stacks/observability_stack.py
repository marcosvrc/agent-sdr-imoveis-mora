from aws_cdk import Stack, aws_cloudwatch as cw
from constructs import Construct


class ObservabilityStack(Stack):
    """Dashboard CloudWatch: latência do agente, mensagens/min, erros na DLQ, tokens Bedrock. X-Ray habilitado nas Lambdas.
    Tracing de LLM (prompts, custos por conversa): Langfuse (opcional, container ou cloud) via callback do LangChain."""
    def __init__(self, scope: Construct, id: str, **kw):
        super().__init__(scope, id, **kw)
        cw.Dashboard(self, "Dash", dashboard_name="sdr-poc", widgets=[[
            cw.GraphWidget(title="Agent: duração", left=[cw.Metric(namespace="AWS/Lambda", metric_name="Duration",
                                                                    dimensions_map={"FunctionName": "sdr-agent"})]),
            cw.GraphWidget(title="DLQ", left=[cw.Metric(namespace="AWS/SQS", metric_name="ApproximateNumberOfMessagesVisible",
                                                        dimensions_map={"QueueName": "sdr-dlq.fifo"})]),
            cw.GraphWidget(title="Bedrock tokens", left=[cw.Metric(namespace="AWS/Bedrock", metric_name="InputTokenCount"),
                                                         cw.Metric(namespace="AWS/Bedrock", metric_name="OutputTokenCount")]),
        ]])
