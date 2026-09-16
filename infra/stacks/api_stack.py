from aws_cdk import Stack, aws_lambda as _lambda, aws_apigatewayv2 as apigw, aws_cognito as cognito, \
    aws_ec2 as ec2, aws_rds as rds
from aws_cdk.aws_apigatewayv2_integrations import HttpLambdaIntegration
from aws_cdk.aws_apigatewayv2_authorizers import HttpJwtAuthorizer
from constructs import Construct


class ApiStack(Stack):
    """FastAPI em Lambda: catálogo e eventos sem auth, o resto atrás do JWT do Cognito.

    A lista de rotas aqui precisa acompanhar os routers do `main.py` — ver comentário abaixo."""
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, lambda_sg: ec2.SecurityGroup, cluster: rds.DatabaseCluster, queues, **kw):
        super().__init__(scope, id, **kw)
        pool = cognito.UserPool(self, "Corretores", user_pool_name="sdr-corretores", self_sign_up_enabled=False)
        client = pool.add_client("Dashboard", auth_flows=cognito.AuthFlow(user_srp=True))

        fn = _lambda.DockerImageFunction(
            self, "ApiFn", code=_lambda.DockerImageCode.from_image_asset("..", file="services/api/Dockerfile"),
            architecture=_lambda.Architecture.ARM_64, vpc=vpc, security_groups=[lambda_sg], memory_size=1024,
            environment={"SDR_PROFILE": "aws"})
        cluster.secret.grant_read(fn); cluster.connections.allow_default_port_from(fn)
        for q in queues.outbound.values():
            q.grant_send_messages(fn)          # handoff: corretor responde pelo canal do lead

        auth = HttpJwtAuthorizer("Jwt", pool.user_pool_provider_url, jwt_audience=[client.user_pool_client_id])
        api = apigw.HttpApi(self, "Api", api_name="sdr-api",
                            cors_preflight=apigw.CorsPreflightOptions(allow_origins=["*"], allow_methods=[apigw.CorsHttpMethod.ANY], allow_headers=["*"]))
        integ = HttpLambdaIntegration("ApiInt", fn)

        # As duas listas abaixo espelham os `include_router` de services/api/src/api/main.py. Elas
        # existiam com cinco prefixos enquanto a aplicação já tinha catorze: no perfil aws o painel
        # não configurava modelo, não via governança, não auditava e não cadastrava corretor —
        # rotas simplesmente não existiam no API Gateway. Prefixo novo no main.py entra aqui também.
        PUBLICAS = ("/imoveis", "/eventos", "/health", "/fotos")
        PROTEGIDAS = ("/leads", "/dashboard", "/handoff", "/interesses", "/reativacao",
                      "/clientes", "/notificacoes", "/corretores", "/config", "/governanca",
                      "/auditoria", "/calendario")

        for prefixo in PUBLICAS:
            for caminho in (prefixo, f"{prefixo}/{{proxy+}}"):
                api.add_routes(path=caminho, methods=[apigw.HttpMethod.ANY], integration=integ)

        # O retorno do OAuth do Google chega SEM credencial do painel — quem autentica é o `state`
        # assinado (ADR-0008). Rota estática ganha da greedy no API Gateway, então ela fica pública
        # mesmo com /calendario/{proxy+} protegido logo abaixo.
        api.add_routes(path="/calendario/callback", methods=[apigw.HttpMethod.GET], integration=integ)

        for prefixo in PROTEGIDAS:
            for caminho in (prefixo, f"{prefixo}/{{proxy+}}"):
                api.add_routes(path=caminho, methods=[apigw.HttpMethod.ANY], integration=integ, authorizer=auth)

        self.url = api.url
