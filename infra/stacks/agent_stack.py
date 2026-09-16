from aws_cdk import Stack, Duration, aws_lambda as _lambda, aws_ec2 as ec2, aws_rds as rds, aws_iam as iam
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from constructs import Construct


class AgentStack(Stack):
    """Lambda container do agente consumindo SQS inbound. ADR-0002."""
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, lambda_sg: ec2.SecurityGroup, cluster: rds.DatabaseCluster, queues, ai, scheduler_role_arn: str, **kw):
        super().__init__(scope, id, **kw)
        ambiente = {
            "SDR_DATABASE_DSN": "",                         # resolvido via Secrets Manager no bootstrap
            "SDR_KNOWLEDGE_BASE_ID": ai.kb.attr_knowledge_base_id,
            "SDR_GUARDRAIL_ID": ai.guardrail.attr_guardrail_id,
            "SDR_EVENTBUS_NAME": "sdr-events",
            "SDR_SCHEDULER_GROUP": "sdr-followup",
            "INBOUND_QUEUE_ARN": queues.inbound.queue_arn,
            "SCHEDULER_ROLE_ARN": scheduler_role_arn,
        }
        fn = _lambda.DockerImageFunction(
            self, "AgentFn", function_name="sdr-agent",
            code=_lambda.DockerImageCode.from_image_asset("..", file="services/agent/Dockerfile"),
            architecture=_lambda.Architecture.ARM_64, memory_size=2048, timeout=Duration.minutes(3),
            vpc=vpc, security_groups=[lambda_sg], environment=ambiente,
        )
        fn.add_event_source(SqsEventSource(queues.inbound, batch_size=1, report_batch_item_failures=True))
        for q in (*queues.outbound.values(), queues.resumir, queues.events):
            q.grant_send_messages(fn)

        # Resumidor: mesma imagem, handler diferente, consumindo `sdr-resumir` (fora da conversa)
        resumir_fn = _lambda.DockerImageFunction(
            self, "ResumirFn", function_name="sdr-agent-resumir",
            code=_lambda.DockerImageCode.from_image_asset("..", file="services/agent/Dockerfile", cmd=["agent.eventos.handler"]),
            architecture=_lambda.Architecture.ARM_64, memory_size=1024, timeout=Duration.minutes(2), vpc=vpc, security_groups=[lambda_sg],
            environment=ambiente)
        resumir_fn.add_event_source(SqsEventSource(queues.resumir, batch_size=1))
        cluster.secret.grant_read(resumir_fn)
        resumir_fn.add_to_role_policy(iam.PolicyStatement(actions=["bedrock:InvokeModel"], resources=["*"]))

        # Reativador: consome `sdr-imovel-novo`, seleciona os leads e devolve um turno por candidato
        # à fila inbound — não fala com o cliente, quem fala é o agente. Sem Bedrock, por isso.
        reativador_fn = _lambda.DockerImageFunction(
            self, "ReativadorFn", function_name="sdr-agent-reativador",
            code=_lambda.DockerImageCode.from_image_asset("..", file="services/agent/Dockerfile", cmd=["agent.reativador.handler"]),
            architecture=_lambda.Architecture.ARM_64, memory_size=1024, timeout=Duration.minutes(5), vpc=vpc,
            security_groups=[lambda_sg], environment=ambiente)
        reativador_fn.add_event_source(SqsEventSource(queues.imovel_novo, batch_size=1))
        queues.inbound.grant_send_messages(reativador_fn)
        queues.imovel_novo.grant_send_messages(fn)
        cluster.secret.grant_read(reativador_fn)
        queues.bus.grant_put_events_to(fn)
        cluster.secret.grant_read(fn)
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream", "bedrock:Retrieve",
                     "bedrock:ApplyGuardrail", "transcribe:*", "scheduler:CreateSchedule", "scheduler:UpdateSchedule",
                     "scheduler:DeleteSchedule", "iam:PassRole"], resources=["*"]))
        # Demo: elimina cold start (alias na função, não na versão — evita recriar a cada update)
        fn.add_alias("live", provisioned_concurrent_executions=1)
