FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends gammu curl && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir requests python-gammu schedule
COPY vigia.py .
CMD ["python", "-u", "vigia.py"]
