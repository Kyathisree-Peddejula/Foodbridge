# FoodBridge Django API - build context is the repository root
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
# strip Windows line endings so the script runs on Linux, then make it executable
RUN sed -i 's/\r$//' /entrypoint.sh && chmod +x /entrypoint.sh && rm -f /app/backend/db.sqlite3
WORKDIR /app/backend
ENV DJANGO_DEBUG=false DATASET_DIR=/app/data/freshretailnet
EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["web"]