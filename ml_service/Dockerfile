# Build context: repository root  (docker build -f ml_service/Dockerfile .)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends curl build-essential && rm -rf /var/lib/apt/lists/*
# CPU-only PyTorch keeps the image ~1 GB smaller
RUN pip install --index-url https://download.pytorch.org/whl/cpu "torch>=2.2"
COPY ml_service/requirements.txt /app/ml_service/requirements.txt
RUN pip install -r /app/ml_service/requirements.txt
COPY ml_service /app/ml_service
COPY scripts /app/scripts
COPY data /app/data
WORKDIR /app/ml_service
ENV DATASET_DIR=/app/data/freshretailnet ARTIFACTS_DIR=/app/ml_service/artifacts
EXPOSE 8001
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fs http://localhost:8001/health || exit 1
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8001}"]
