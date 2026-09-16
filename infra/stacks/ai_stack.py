from aws_cdk import Stack, aws_bedrock as bedrock, aws_iam as iam, aws_rds as rds, aws_s3 as s3
from constructs import Construct


class AiStack(Stack):
    """Bedrock Knowledge Base (vector store Aurora pgvector) + Guardrails. ADR-0001."""
    def __init__(self, scope: Construct, id: str, cluster: rds.DatabaseCluster, bucket: s3.Bucket, **kw):
        super().__init__(scope, id, **kw)
        role = iam.Role(self, "KbRole", assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"))
        bucket.grant_read(role)
        cluster.secret.grant_read(role)
        role.add_to_policy(iam.PolicyStatement(actions=["rds-data:ExecuteStatement", "rds-data:BatchExecuteStatement",
                                                        "rds:DescribeDBClusters", "bedrock:InvokeModel"], resources=["*"]))

        self.kb = bedrock.CfnKnowledgeBase(
            self, "Kb", name="sdr-imoveis", role_arn=role.role_arn,
            knowledge_base_configuration={"type": "VECTOR", "vectorKnowledgeBaseConfiguration": {
                "embeddingModelArn": f"arn:aws:bedrock:{self.region}::foundation-model/amazon.titan-embed-text-v2:0"}},
            storage_configuration={"type": "RDS", "rdsConfiguration": {
                "resourceArn": cluster.cluster_arn, "credentialsSecretArn": cluster.secret.secret_arn,
                "databaseName": "sdr", "tableName": "bedrock_integration.bedrock_kb",
                "fieldMapping": {"primaryKeyField": "id", "vectorField": "embedding",
                                 "textField": "chunks", "metadataField": "metadata"}}},
        )
        # Imóveis: NO chunking (um arquivo = um chunk). Documentos: hierárquico.
        self.ds_imoveis = bedrock.CfnDataSource(
            self, "DsImoveis", name="imoveis", knowledge_base_id=self.kb.attr_knowledge_base_id,
            data_source_configuration={"type": "S3", "s3Configuration": {
                "bucketArn": bucket.bucket_arn, "inclusionPrefixes": ["imoveis/"]}},
            vector_ingestion_configuration={"chunkingConfiguration": {"chunkingStrategy": "NONE"}},
        )
        self.ds_docs = bedrock.CfnDataSource(
            self, "DsDocs", name="documentos", knowledge_base_id=self.kb.attr_knowledge_base_id,
            data_source_configuration={"type": "S3", "s3Configuration": {
                "bucketArn": bucket.bucket_arn, "inclusionPrefixes": ["documentos/"]}},
            vector_ingestion_configuration={"chunkingConfiguration": {
                "chunkingStrategy": "HIERARCHICAL", "hierarchicalChunkingConfiguration": {
                    "levelConfigurations": [{"maxTokens": 1500}, {"maxTokens": 300}], "overlapTokens": 60}}},
        )
        self.guardrail = bedrock.CfnGuardrail(
            self, "Guardrail", name="sdr-guardrail",
            blocked_input_messaging="Não posso ajudar com isso, mas posso te ajudar a encontrar um imóvel.",
            blocked_outputs_messaging="Vou pedir para um corretor te retornar sobre isso.",
            # CPF não existe na lista de PII do Bedrock: entra como regex própria.
            sensitive_information_policy_config={
                "piiEntitiesConfig": [{"type": "CREDIT_DEBIT_CARD_NUMBER", "action": "BLOCK"},
                                      {"type": "US_BANK_ACCOUNT_NUMBER", "action": "BLOCK"},
                                      {"type": "EMAIL", "action": "ANONYMIZE"}],
                "regexesConfig": [{"name": "cpf", "action": "ANONYMIZE", "description": "CPF brasileiro",
                                   "pattern": r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b"}]},
            topic_policy_config={"topicsConfig": [{"name": "aconselhamento-financeiro", "type": "DENY",
                "definition": "Recomendações específicas de investimento financeiro fora do mercado imobiliário",
                "examples": ["Devo comprar ações?", "Qual criptomoeda investir?"]}]},
        )
