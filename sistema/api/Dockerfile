FROM python:3.12-slim AS deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# Timeout e retentativas maiores: as rodas do faster-whisper (ctranslate2, onnxruntime)
# têm dezenas de MB e estouram o timeout padrão em redes lentas
RUN pip install --no-cache-dir --default-timeout=120 --retries 10 -r requirements.txt

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
COPY . .
# Modelo de transcrição baixado no build: o servidor transcreve sem acesso à internet
ARG WHISPER_MODEL=base
ENV HF_HOME=/app/.cache/huggingface HF_HUB_DISABLE_TELEMETRY=1 WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"
RUN useradd -m -u 1001 cesup && chown -R cesup:cesup /app
USER cesup
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
