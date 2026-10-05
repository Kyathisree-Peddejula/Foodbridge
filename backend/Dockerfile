# Build context: repository root  (docker build -f backend/Dockerfile .)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install -r /app/backend/requirements.txt
COPY backend /app/backend
COPY scripts /app/scripts
COPY data /app/data
COPY deploy/backend-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && rm -f /app/backend/db.sqlite3
WORKDIR /app/backend
ENV DJANGO_DEBUG=false DATASET_DIR=/app/data/freshretailnet
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD sh -c "curl -fs http://localhost:${PORT:-8000}/api/health/ || exit 1"
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]
