# FoodBridge ML service on a Hugging Face Docker Space (free CPU: 2 vCPU / 16 GB RAM)
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    DATASET_DIR=/home/user/app/data/freshretailnet ARTIFACTS_DIR=/home/user/app/ml_service/artifacts \
    ENABLE_SCHEDULER=false PORT=7860
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl && rm -rf /var/lib/apt/lists/*
# Spaces run as uid 1000
RUN useradd -m -u 1000 user
USER user
ENV PATH=/home/user/.local/bin:$PATH
WORKDIR /home/user/app
RUN pip install --user --index-url https://download.pytorch.org/whl/cpu "torch>=2.2"
COPY --chown=user ml_service/requirements.txt ml_service/requirements.txt
RUN pip install --user -r ml_service/requirements.txt
COPY --chown=user . .
WORKDIR /home/user/app/ml_service
EXPOSE 7860
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
