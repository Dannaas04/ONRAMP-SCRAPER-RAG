FROM python:3.11-slim

WORKDIR /code

RUN apt-get update && apt-get install -y --no-install-recommends \
    wget gnupg curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --timeout 120 --retries 15 \
    fastapi==0.115.0 uvicorn[standard]==0.30.6 httpx==0.27.2 tenacity==9.0.0
RUN pip install --no-cache-dir --timeout 120 --retries 15 \
    celery==5.4.0 redis==5.0.8 requests==2.32.3 beautifulsoup4==4.12.3
RUN pip install --no-cache-dir --timeout 120 --retries 15 \
    sqlmodel==0.0.22 psycopg2-binary==2.9.9 pgvector==0.3.6
RUN pip install --no-cache-dir --timeout 120 --retries 15 \
    playwright==1.47.0
RUN python -m playwright install chromium

COPY app ./app

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]