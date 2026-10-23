-- Criar banco keycloak se não existir (idempotente)
SELECT 'CREATE DATABASE keycloak WITH ENCODING=''UTF8'''
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'keycloak')\gexec

-- Garantir permissões
GRANT ALL PRIVILEGES ON DATABASE keycloak TO cesup;
