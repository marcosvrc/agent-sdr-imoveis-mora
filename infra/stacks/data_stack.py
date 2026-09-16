from aws_cdk import Stack, RemovalPolicy, aws_rds as rds, aws_ec2 as ec2, aws_s3 as s3
from constructs import Construct


class DataStack(Stack):
    """Aurora Serverless v2 (Postgres 16 + pgvector, escala a 0) e bucket S3 da base de imóveis/documentos."""
    def __init__(self, scope: Construct, id: str, vpc: ec2.Vpc, lambda_sg: ec2.SecurityGroup, **kw):
        super().__init__(scope, id, **kw)
        self.cluster = rds.DatabaseCluster(
            self, "Aurora",
            engine=rds.DatabaseClusterEngine.aurora_postgres(version=rds.AuroraPostgresEngineVersion.VER_16_4),
            vpc=vpc, serverless_v2_min_capacity=0, serverless_v2_max_capacity=2,
            writer=rds.ClusterInstance.serverless_v2("writer"),
            default_database_name="sdr", enable_data_api=True,          # Data API: Knowledge Base usa para acessar o vector store
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.cluster.connections.allow_default_port_from(lambda_sg, "Lambdas do SDR")
        self.bucket = s3.Bucket(self, "Corpus", removal_policy=RemovalPolicy.DESTROY, auto_delete_objects=True)
        # schema.sql aplicado por Custom Resource (Lambda + Data API) — ver scripts/apply_schema.py
