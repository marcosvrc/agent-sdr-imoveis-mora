-- Banco do CRM imobiliário, separado do `sdr` (docs/decisions.md, D-01 e D-02).
--
-- Separado, e não um schema dentro do banco da Mora, porque é o que torna a regra verificável: uma
-- consulta cruzada precisaria de OUTRA conexão, e isso aparece na revisão. No mesmo schema, o
-- primeiro JOIN entre `leads` e `opportunities` pareceria inofensivo — e a partir dali ninguém mais
-- saberia dizer quem é dono de um cliente.
--
-- Roda antes de schema.sql (ordem alfabética no docker-entrypoint-initdb.d).
SELECT 'CREATE DATABASE crm' WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'crm')\gexec
