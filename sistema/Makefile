.PHONY: setup up down restart logs ps build clean migrate db sh \
        garage-setup zabbix-setup garage-key garage-status health zabbix-logs glpi-logs glpi-token

# Setup completo (primeira vez)
setup:
	chmod +x setup.sh && ./setup.sh

# Subir todos os containers
up:
	docker compose up -d

# Parar tudo
down:
	docker compose down

# Reiniciar
restart:
	docker compose restart

# Build das imagens
build:
	docker compose build --no-cache api pwa-builder

# Logs de todos
logs:
	docker compose logs -f

# Log de um container: make log s=api
log:
	docker compose logs -f $(s)

# Status
ps:
	docker compose ps

# Shell em um container: make sh s=api
sh:
	docker compose exec $(s) sh

# Apaga tudo incluindo volumes
clean:
	docker compose down -v --remove-orphans

# Reinstalação completa (apaga tudo e instala do zero)
reinstalar:
	bash reinstalar.sh

# Migrações Alembic
migrate:
	docker compose exec api alembic upgrade head

# psql direto no banco
db:
	docker compose exec postgres psql -U cesup -d incidentes

# MySQL do Zabbix/GLPI
db-mysql:
	docker compose exec mysql mysql -u root -p${MYSQL_ROOT_PASSWORD}

# Configurar Garage S3 (layout, bucket, chave no .env) — idempotente
garage-setup:
	bash garage-setup.sh

# Criar chave S3 manualmente
garage-key:
	docker compose exec garage /garage key create cesup-api
	docker compose exec garage /garage bucket allow --read --write --owner evidencias --key cesup-api

# Status do Garage
garage-status:
	docker compose exec garage /garage status

# Saúde de todos os containers
health:
	@docker compose ps
	@echo ""
	@docker inspect --format='{{.Name}}: {{.State.Health.Status}}' 		$$(docker compose ps -q) 2>/dev/null || true

# Configurar Zabbix via API (usuário, webhook, ação, host) — idempotente
zabbix-setup:
	bash zabbix-setup.sh

# Logs do Zabbix
zabbix-logs:
	docker compose logs -f zabbix-server zabbix-web

# Logs do GLPI
glpi-logs:
	docker compose logs -f glpi

# Salvar tokens do GLPI no .env após configuração manual
glpi-token:
	@echo "Cole o App Token do GLPI:" && read APP && 	 sed -i "s|^GLPI_APP_TOKEN=.*|GLPI_APP_TOKEN=$$APP|" .env && 	 echo "Cole o User Token do GLPI:" && read USR && 	 sed -i "s|^GLPI_USER_TOKEN=.*|GLPI_USER_TOKEN=$$USR|" .env && 	 docker compose up -d api worker beat && docker compose exec -T nginx nginx -s reload && 	 echo "Tokens salvos e containers recriados."
