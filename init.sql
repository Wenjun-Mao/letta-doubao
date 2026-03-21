-- Title: Init Letta Database

\set db_user `([ -r /var/run/secrets/letta-user ] && cat /var/run/secrets/letta-user) || echo "${POSTGRES_USER:-letta}"`
\set db_password `([ -r /var/run/secrets/letta-password ] && cat /var/run/secrets/letta-password) || echo "${POSTGRES_PASSWORD:-letta}"`
\set db_name `([ -r /var/run/secrets/letta-db ] && cat /var/run/secrets/letta-db) || echo "${POSTGRES_DB:-letta}"`

\c :"db_name"

CREATE SCHEMA :"db_name"
    AUTHORIZATION :"db_user";

ALTER DATABASE :"db_name"
    SET search_path TO :"db_name";

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA :"db_name";

DROP SCHEMA IF EXISTS public CASCADE;
