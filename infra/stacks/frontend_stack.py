from pathlib import Path
from aws_cdk import Stack, CfnOutput, aws_s3 as s3, aws_cloudfront as cf, aws_cloudfront_origins as origins, \
    aws_s3_deployment as deploy, RemovalPolicy
from constructs import Construct


class FrontendStack(Stack):
    """Site vitrine (PWA) e painel do corretor como sites estáticos: S3 + CloudFront.

    O upload dos arquivos só entra na stack se `apps/<app>/dist` existir — assim `cdk synth`
    roda na CI sem buildar os fronts, e `make deploy` (que faz `npm run build` antes) publica
    de verdade. Alternativa gerenciada: Amplify Hosting ligado ao repositório.
    """
    APPS = ("web", "dashboard")

    # O build da vitrine grava um HTML por rota (apps/web/scripts/gerar-paginas.mjs) com título,
    # descrição, Open Graph e dado estruturado próprios. No S3 esses arquivos são
    # `imovel/<slug>/index.html`; sem esta função, `/imovel/<slug>` devolve 404, cai na regra de SPA
    # e o rastreador recebe o index genérico — o prerender não serviria para nada.
    REESCRITA_INDEX = """
function handler(event) {
  var req = event.request;
  var uri = req.uri;
  if (uri.endsWith('/')) { req.uri = uri + 'index.html'; }
  else if (!uri.split('/').pop().includes('.')) { req.uri = uri + '/index.html'; }
  return req;
}
"""

    def __init__(self, scope: Construct, id: str, api_url: str, ws_url: str, **kw):
        super().__init__(scope, id, **kw)
        for app_name in self.APPS:
            bucket = s3.Bucket(self, f"{app_name}Bucket", removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
            # Só a vitrine tem páginas pré-geradas; o painel é SPA autenticada e não é indexado.
            funcoes = []
            if app_name == "web":
                fn = cf.Function(self, "ReescritaIndex", code=cf.FunctionCode.from_inline(self.REESCRITA_INDEX),
                                 runtime=cf.FunctionRuntime.JS_2_0,
                                 comment="/rota -> /rota/index.html (páginas pré-geradas da vitrine)")
                funcoes = [cf.FunctionAssociation(function=fn, event_type=cf.FunctionEventType.VIEWER_REQUEST)]

            dist = cf.Distribution(
                self, f"{app_name}Dist",
                default_behavior=cf.BehaviorOptions(origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                                                    viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                                                    function_associations=funcoes),
                default_root_object="index.html",
                # Rota sem arquivo pré-gerado (filtro combinado, link velho) volta para o shell e o
                # React Router resolve. 404 continua 404 para o buscador não indexar página fantasma.
                error_responses=[cf.ErrorResponse(http_status=403, response_http_status=200, response_page_path="/index.html"),
                                 cf.ErrorResponse(http_status=404, response_http_status=404, response_page_path="/index.html")])
            build = Path(__file__).parents[2] / "apps" / app_name / "dist"
            if build.is_dir():
                deploy.BucketDeployment(self, f"{app_name}Deploy", destination_bucket=bucket, distribution=dist,
                                        sources=[deploy.Source.asset(str(build))])
            else:
                CfnOutput(self, f"{app_name}BuildAusente",
                          value=f"rode `npm run build` em apps/{app_name} antes do deploy para publicar os arquivos")
            CfnOutput(self, f"{app_name}Url", value=f"https://{dist.distribution_domain_name}")
            # As VITE_* são compiladas no bundle: a stack publica o que a máquina de quem rodou
            # `make deploy` construiu. Fica registrado no output porque não há como a infra corrigir
            # depois — só reconstruindo e republicando.
            if app_name == "dashboard":
                CfnOutput(self, "PainelLogin",
                          value=("exige VITE_COGNITO_USER_POOL_ID e VITE_COGNITO_CLIENT_ID no build; "
                                 "sem elas o painel publicado usa o login de desenvolvimento"))
        CfnOutput(self, "ApiUrl", value=api_url)
        CfnOutput(self, "WsUrl", value=ws_url)
