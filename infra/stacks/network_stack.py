from aws_cdk import Stack, aws_ec2 as ec2
from constructs import Construct


class NetworkStack(Stack):
    """VPC mínima: Aurora exige VPC; Lambdas do agent/api entram nela. NAT só para Bedrock/Meta (ou VPC endpoints)."""
    def __init__(self, scope: Construct, id: str, **kw):
        super().__init__(scope, id, **kw)
        self.vpc = ec2.Vpc(self, "Vpc", max_azs=2, nat_gateways=1)
        # SG único para todas as Lambdas em VPC. Fica aqui (e não em cada stack) para evitar
        # ciclo de dependência: a regra de entrada no Aurora referencia este SG, não as funções.
        self.lambda_sg = ec2.SecurityGroup(self, "LambdaSg", vpc=self.vpc, allow_all_outbound=True,
                                           description="Lambdas do SDR (agent, api, canais)")
        # Reduz custo/latência: endpoints para Bedrock, SQS, Secrets Manager
        for name, svc in {"Bedrock": ec2.InterfaceVpcEndpointAwsService.BEDROCK_RUNTIME,
                          "Sqs": ec2.InterfaceVpcEndpointAwsService.SQS,
                          "Secrets": ec2.InterfaceVpcEndpointAwsService.SECRETS_MANAGER}.items():
            self.vpc.add_interface_endpoint(name, service=svc)
