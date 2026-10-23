#!/bin/bash
# Executado (via source) pelo entrypoint do MySQL na primeira inicialização.
# A senha vem de MYSQL_GLPI_PASSWORD (docker-compose.yml → .env).
docker_process_sql <<-EOSQL
	CREATE DATABASE IF NOT EXISTS glpi CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
	CREATE USER IF NOT EXISTS 'glpi'@'%' IDENTIFIED BY '${MYSQL_GLPI_PASSWORD}';
	GRANT ALL PRIVILEGES ON glpi.* TO 'glpi'@'%';
	FLUSH PRIVILEGES;
EOSQL
