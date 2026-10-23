"""Cliente S3 Garage para upload de evidências (fotos, áudios)."""
import boto3, uuid
from botocore.client import Config
from app.core.config import settings
import logging

log = logging.getLogger("s3_client")

def _client():
    return boto3.client(
        "s3",
        endpoint_url=settings.S3_ENDPOINT,
        aws_access_key_id=settings.S3_ACCESS_KEY,
        aws_secret_access_key=settings.S3_SECRET_KEY,
        config=Config(signature_version="s3v4"),
        region_name="us-east-1",
    )

def upload_evidencia(dados: bytes, content_type: str, extensao: str = "bin") -> str | None:
    """Faz upload de uma evidência e retorna a URL pública."""
    try:
        key = f"evidencias/{uuid.uuid4()}.{extensao}"
        _client().put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=dados,
            ContentType=content_type,
            ACL="public-read",
        )
        return f"{settings.S3_ENDPOINT}/{settings.S3_BUCKET}/{key}"
    except Exception as e:
        log.error(f"Erro no upload S3: {e}")
        return None

def url_presigned(key: str, expira_segundos: int = 3600) -> str | None:
    """Gera URL assinada para acesso temporário a uma evidência."""
    try:
        return _client().generate_presigned_url(
            "get_object",
            Params={"Bucket": settings.S3_BUCKET, "Key": key},
            ExpiresIn=expira_segundos,
        )
    except Exception as e:
        log.error(f"Erro ao gerar URL: {e}")
        return None
