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
    # Keycloak (Sprint 2): a API valida o token OIDC emitido para estes clients
    KEYCLOAK_URL: str = "http://keycloak:8080/auth"
    KEYCLOAK_REALM: str = "cesup"
    KEYCLOAK_CLIENT_ID: str = "incidentes-api"
    KEYCLOAK_CLIENT_SECRET: str = "secret123"
    KEYCLOAK_CLIENTES_ACEITOS: str = "incidentes-pwa,incidentes-cli"
    # Sem token, a API recusa (401). Desligado, quem não se identifica age como "anônimo"
    AUTH_OBRIGATORIA: bool = False
    # Token de serviço: webhook do Zabbix, ingestão de e-mail e scripts internos
    TOKEN_SERVICO: str = ""
    # SMTP
    SMTP_HOST: str = "smtp.ufrgs.br"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    # Plantão (Sprint 4): listas separadas por vírgula; o 2º nível entra no reescalonamento
    PLANTAO_PHONE: str = ""
    PLANTAO_EMAIL: str = ""
    PLANTAO_ESCALONAMENTO_PHONE: str = ""
    PLANTAO_ESCALONAMENTO_EMAIL: str = ""
    LIGACAO_P1: bool = True                 # P1 também liga pelo modem GSM, além do SMS
    VIGIA_TOKEN:   str = "vigia-token-cesup-2026"
    # Transcrição de voz (faster-whisper, local): tiny | base | small | large-v3
    WHISPER_MODEL: str = "base"
    WHISPER_DEVICE: str = "auto"            # auto: GPU (cuda) se houver, senão CPU
    # IA no cluster GPU (Sprints 5–6), API compatível com a OpenAI (vLLM). Vazio = sem IA:
    # o sistema segue funcionando (degradação graciosa)
    VISION_URL: str = ""                    # ex.: http://gpu.cesup:8000/v1
    VISION_MODEL: str = "Qwen2-VL-7B-Instruct"
    EMBEDDINGS_URL: str = ""                # ex.: http://gpu.cesup:8001/v1
    EMBEDDINGS_MODEL: str = "bge-m3"
    IA_API_KEY: str = ""
    IA_TIMEOUT_S: float = 20.0
    # Correlação (Sprint 6) e deduplicação (Sprint 3)
    CORRELACAO_JANELA_HORAS: int = 4
    DEDUP_JANELA_HORAS: int = 24
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


def lista(valor: str) -> list[str]:
    """'a, b,,c' → ['a', 'b', 'c'] (variáveis de ambiente com vários valores)."""
    return [v.strip() for v in (valor or "").split(",") if v.strip()]
