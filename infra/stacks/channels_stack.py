from aws_cdk import Stack, Duration, CfnOutput, aws_lambda as _lambda, aws_apigatewayv2 as apigw, aws_dynamodb as ddb, \
    aws_secretsmanager as sm, aws_ec2 as ec2, aws_rds as rds
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration, WebSocketLambdaIntegration
from aws_cdk.aws_lambda_event_sources import SqsEventSource
from constructs import Construct


class ChannelsStack(Stack):
    """Telegram (webhook HTTP) e Web (WebSocket). ADR-0003 e ADR-0007.

    **Telegram é o canal ativo** (ADR-0007: sem aprovação da Meta, sem janela de 24h, sem template).
    No perfil local ele roda por long polling; aqui, por webhook — long polling exige um processo
    vivo, e Lambda não é isso. É a única diferença entre os dois perfis para este canal: o mesmo
    `parse_inbound` traduz o update nos dois casos.

    **WhatsApp fica atrás de um interruptor** (`cdk deploy -c whatsapp=true`). O adaptador continua
    no repositório e o perfil local ainda serve o webhook dele; o que não faz sentido é provisionar
    por padrão um canal que a decisão vigente descartou — era essa a contradição entre o ADR-0007 e
    esta stack.
    """
    def __init__(self, scope: Construct, id: str, queues, vpc: ec2.Vpc, lambda_sg: ec2.SecurityGroup, cluster: rds.DatabaseCluster, **kw):
        super().__init__(scope, id, **kw)

        # ---- Telegram (canal ativo) ----
        tg_secret = sm.Secret(self, "TgSecret", secret_name="sdr/telegram")   # bot_token, webhook_path
        # Container (não zip): os canais dependem de sdr_shared, psycopg e httpx — ver services/*/Dockerfile
        tg_img = lambda cmd: _lambda.DockerImageCode.from_image_asset(
            "..", file="services/channels/telegram/Dockerfile", cmd=[cmd])
        tg_in = _lambda.DockerImageFunction(self, "TgInbound", code=tg_img("canal_telegram.inbound.handler"),
                                            architecture=_lambda.Architecture.ARM_64, vpc=vpc, security_groups=[lambda_sg],
                                            timeout=Duration.seconds(10), environment={"SDR_PROFILE": "aws"})
        tg_out = _lambda.DockerImageFunction(self, "TgOutbound", code=tg_img("canal_telegram.outbound.handler"),
                                             architecture=_lambda.Architecture.ARM_64, vpc=vpc, security_groups=[lambda_sg],
                                             timeout=Duration.seconds(30), environment={"SDR_PROFILE": "aws"})
        queues.inbound.grant_send_messages(tg_in)
        tg_out.add_event_source(SqsEventSource(queues.outbound["telegram"], batch_size=5))
        for f in (tg_in, tg_out):
            tg_secret.grant_read(f); cluster.secret.grant_read(f)

        # O Telegram não assina o corpo do update (diferente da Meta, que manda HMAC). A proteção é
        # o caminho secreto na URL do webhook: só quem recebeu o `setWebhook` sabe chamá-lo.
        caminho = self.node.try_get_context("telegram_webhook_path") or "/webhook/troque-este-segredo"
        tg_http = apigw.HttpApi(self, "TgWebhook", api_name="sdr-telegram-webhook")
        tg_http.add_routes(path=caminho, methods=[apigw.HttpMethod.POST],
                           integration=HttpLambdaIntegration("TgInt", tg_in))
        self.telegram_webhook_url = f"{tg_http.url}{caminho.lstrip('/')}"
        CfnOutput(self, "TelegramWebhook", value=self.telegram_webhook_url,
                  description="Registre com: curl -F url=<esta URL> https://api.telegram.org/bot<TOKEN>/setWebhook")

        # ---- WhatsApp (desligado por padrão — ADR-0007) ----
        if self.node.try_get_context("whatsapp"):
            wa_secret = sm.Secret(self, "WaSecret", secret_name="sdr/whatsapp")   # token, app_secret, phone_number_id
            wa_img = lambda cmd: _lambda.DockerImageCode.from_image_asset(
                "..", file="services/channels/whatsapp/Dockerfile", cmd=[cmd])
            wa_in = _lambda.DockerImageFunction(self, "WaInbound", code=wa_img("canal_whatsapp.inbound.handler"),
                                                architecture=_lambda.Architecture.ARM_64, vpc=vpc, security_groups=[lambda_sg], timeout=Duration.seconds(10),
                                                environment={"SDR_PROFILE": "aws"})
            wa_out = _lambda.DockerImageFunction(self, "WaOutbound", code=wa_img("canal_whatsapp.outbound.handler"),
                                                 architecture=_lambda.Architecture.ARM_64, vpc=vpc, security_groups=[lambda_sg], timeout=Duration.seconds(30),
                                                 environment={"SDR_PROFILE": "aws"})
            queues.inbound.grant_send_messages(wa_in)
            wa_out.add_event_source(SqsEventSource(queues.outbound["whatsapp"], batch_size=5))
            for f in (wa_in, wa_out):
                wa_secret.grant_read(f); cluster.secret.grant_read(f)
            http = apigw.HttpApi(self, "WaWebhook", api_name="sdr-whatsapp-webhook")
            http.add_routes(path="/webhook", methods=[apigw.HttpMethod.GET, apigw.HttpMethod.POST],
                            integration=HttpLambdaIntegration("WaInt", wa_in))

        # ---- Web chat + tempo real do dashboard ----
        table = ddb.Table(self, "WsConnections", table_name="sdr-ws-connections",
                          partition_key=ddb.Attribute(name="connection_id", type=ddb.AttributeType.STRING),
                          billing_mode=ddb.BillingMode.PAY_PER_REQUEST)
        web_img = lambda cmd: _lambda.DockerImageCode.from_image_asset(
            "..", file="services/channels/web/Dockerfile", cmd=[cmd])
        web_in = _lambda.DockerImageFunction(self, "WebInbound", code=web_img("canal_web.inbound.handler"),
                                             architecture=_lambda.Architecture.ARM_64,
                                             environment={"SDR_PROFILE": "aws", "WS_TABLE": table.table_name})
        ws = apigw.WebSocketApi(self, "WsApi", api_name="sdr-ws",
                                connect_route_options=apigw.WebSocketRouteOptions(integration=WebSocketLambdaIntegration("C", web_in)),
                                disconnect_route_options=apigw.WebSocketRouteOptions(integration=WebSocketLambdaIntegration("D", web_in)),
                                default_route_options=apigw.WebSocketRouteOptions(integration=WebSocketLambdaIntegration("M", web_in)))
        stage = apigw.WebSocketStage(self, "WsStage", web_socket_api=ws, stage_name="v1", auto_deploy=True)
        web_out = _lambda.DockerImageFunction(self, "WebOutbound", code=web_img("canal_web.outbound.handler"),
                                              architecture=_lambda.Architecture.ARM_64,
                                              environment={"WS_TABLE": table.table_name, "WS_ENDPOINT": stage.callback_url})
        web_out.add_event_source(SqsEventSource(queues.outbound["web"], batch_size=5))
        table.grant_read_write_data(web_in); table.grant_read_write_data(web_out)
        queues.inbound.grant_send_messages(web_in); stage.grant_management_api_access(web_out)
        self.ws_url = stage.url
