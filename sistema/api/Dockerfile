FROM python:3.12-slim AS deps
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libpq-dev curl && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
# As rodas do faster-whisper (ctranslate2, onnxruntime) têm dezenas de MB e o download
# do PyPI às vezes trava no meio ("Read timed out"), o que o --retries não cobre.
# O cache do BuildKit guarda o que já baixou e o laço tenta de novo de onde parou.
RUN --mount=type=cache,target=/root/.cache/pip \
    for tentativa in 1 2 3; do \
        pip install --default-timeout=120 --retries 10 -r requirements.txt && exit 0; \
        echo "pip falhou (tentativa $tentativa de 3), tentando de novo..."; sleep 10; \
    done; exit 1

FROM python:3.12-slim AS runtime
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 curl && rm -rf /var/lib/apt/lists/*
COPY --from=deps /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=deps /usr/local/bin /usr/local/bin
# Modelo de transcrição baixado no build: o servidor transcreve sem acesso à internet.
# Fica antes do COPY do código para o cache do Docker não baixá-lo a cada mudança.
ARG WHISPER_MODEL=base
ENV HF_HOME=/app/.cache/huggingface HF_HUB_DISABLE_TELEMETRY=1 WHISPER_MODEL=${WHISPER_MODEL}
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('${WHISPER_MODEL}', device='cpu', compute_type='int8')"
COPY . .
RUN useradd -m -u 1001 cesup && chown -R cesup:cesup /app
USER cesup
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
