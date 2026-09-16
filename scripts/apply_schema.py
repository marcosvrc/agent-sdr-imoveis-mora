"""Aplica shared/sdr_shared/db/schema.sql no Aurora via Data API (não precisa de acesso à VPC)."""
import os
import boto3
sql = open("shared/sdr_shared/db/schema.sql", encoding="utf-8").read()
rds = boto3.client("rds-data")
for stmt in filter(None, (s.strip() for s in sql.split(";"))):
    rds.execute_statement(resourceArn=os.environ["AURORA_ARN"], secretArn=os.environ["AURORA_SECRET_ARN"], database="sdr", sql=stmt)
print("schema aplicado")
