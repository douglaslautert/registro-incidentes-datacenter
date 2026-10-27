from pydantic_settings import BaseSettings
from pydantic import ConfigDict
from typing import List

class Settings(BaseSettings):
    model_config = ConfigDict(extra="ignore", env_file=".env")

    # Banco de incidentes
    DATABASE_URL: str = "postgresql+asyncpg://cesup:cesup123@postgres:5432/incidentes"
    # Fila
    REDIS_URL: str = "redis://:valkey123@valkey:6379/0"
    # S3
    S3_ENDPOINT: str = "http://garage:3900"
    S3_BUCKET: str = "evidencias"
    S3_ACCESS_KEY: str = ""
    S3_SECRET_KEY: str = ""
    # Keycloak
    KEYCLOAK_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "cesup"
    KEYCLOAK_CLIENT_ID: str = "incidentes-api"
    KEYCLOAK_CLIENT_SECRET: str = "secret123"
    # SMTP
    SMTP_HOST: str = "smtp.ufrgs.br"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    # GSM
    PLANTAO_PHONE: str = ""
    VIGIA_TOKEN:   str = "vigia-token-cesup-2026"
    # Transcrição de voz (faster-whisper, local): tiny | base | small
    WHISPER_MODEL: str = "base"
    # Zabbix
    ZABBIX_URL: str = "http://zabbix-web:8080"
    ZABBIX_USER: str = "Admin"
    ZABBIX_PASSWORD: str = "zabbix"
    # GLPI
    GLPI_URL: str = "http://glpi:80"
    GLPI_APP_TOKEN: str = ""
    GLPI_USER_TOKEN: str = ""
    # API
    PUBLIC_URL: str = "http://localhost"
    PUBLIC_WS_URL: str = "ws://localhost"
    SECRET_KEY: str = "dev_secret_key"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "production"
    ALLOWED_ORIGINS: List[str] = ["http://localhost"]

settings = Settings()

