-- Banco separado do Langfuse (perfil observability). Roda antes de schema.sql (ordem alfabética).
SELECT 'CREATE DATABASE langfuse' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'langfuse')\gexec
