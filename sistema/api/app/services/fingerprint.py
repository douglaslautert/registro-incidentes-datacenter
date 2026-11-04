"""Fingerprint de deduplicação (Sprint 3): o mesmo sintoma no mesmo ativo é o mesmo incidente.

Números e pontuação saem da conta: "Temperatura 41 °C" e "temperatura 43C" no mesmo
servidor geram o mesmo fingerprint, assim como o alerta repetido do Zabbix.
"""
import hashlib, re, unicodedata


def normalizar_sintoma(sintoma: str) -> str:
    texto = unicodedata.normalize("NFKD", sintoma or "").encode("ascii", "ignore").decode().lower()
    texto = re.sub(r"[^a-z]+", " ", texto)      # sem números, unidades soltas e pontuação
    return " ".join(p for p in texto.split() if len(p) > 1)


def calcular(ativo_id: str, sintoma: str) -> str:
    base = f"{(ativo_id or '').strip().lower()}|{normalizar_sintoma(sintoma)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]
