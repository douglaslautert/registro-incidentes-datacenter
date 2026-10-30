"""Cliente S3 Garage para evidências (fotos, vídeos, áudios).

O Garage só é acessível dentro da rede Docker e exige pedidos assinados, então
os arquivos são entregues pela própria API (/api/v1/evidencias/arquivo/<chave>).
"""
import boto3, uuid
from botocore.client import Config
from botocore.exceptions import ClientError
from app.core.config import settings
import logging

log = logging.getLogger("s3_client")

ROTA_ARQUIVO = "/api/v1/evidencias/arquivo/"


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
    """Faz upload de uma evidência e retorna o caminho para abri-la pela API."""
    try:
        key = f"evidencias/{uuid.uuid4()}.{extensao}"
        _client().put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=dados,
            ContentType=content_type,
        )
        return ROTA_ARQUIVO + key
    except Exception as e:
        log.error(f"Erro no upload S3: {e}")
        return None


def normalizar_url(url: str) -> str:
    """Converte links antigos (http://garage:3900/evidencias/<chave>, inacessíveis
    fora do Docker) para o caminho servido pela API."""
    prefixo = f"{settings.S3_ENDPOINT.rstrip('/')}/{settings.S3_BUCKET}/"
    return ROTA_ARQUIVO + url[len(prefixo):] if url.startswith(prefixo) else url


class IntervaloInvalido(Exception):
    """Range pedido fora do tamanho do arquivo (HTTP 416)."""


def baixar_evidencia(key: str, intervalo: str | None = None) -> dict | None:
    """Lê uma evidência do S3. `intervalo` é o cabeçalho Range ("bytes=0-1023"),
    necessário para o Safari tocar vídeos. Retorna None se a chave não existir."""
    args = {"Bucket": settings.S3_BUCKET, "Key": key}
    if intervalo:
        args["Range"] = intervalo
    try:
        return _client().get_object(**args)
    except ClientError as e:
        codigo = e.response.get("Error", {}).get("Code", "")
        if codigo in ("NoSuchKey", "404"):
            return None
        if codigo == "InvalidRange":
            raise IntervaloInvalido() from e
        raise


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
