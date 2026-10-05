import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent


class Settings:
    dataset_dir = Path(os.environ.get("DATASET_DIR", REPO / "data" / "freshretailnet"))
    artifacts_dir = Path(os.environ.get("ARTIFACTS_DIR", ROOT / "artifacts"))
    django_url = os.environ.get("DJANGO_API_URL", "http://localhost:8000/api")
    service_key = os.environ.get("SERVICE_API_KEY", "dev-service-key")
    require_service_key = os.environ.get("REQUIRE_SERVICE_KEY", "false").lower() == "true"
    batch_every_hours = float(os.environ.get("BATCH_EVERY_HOURS", "6"))
    enable_scheduler = os.environ.get("ENABLE_SCHEDULER", "true").lower() == "true"
    # training defaults
    lstm_window = 28
    horizon = 14
    lstm_max_series = int(os.environ.get("LSTM_MAX_SERIES", "3000"))
    lstm_epochs = int(os.environ.get("LSTM_EPOCHS", "8"))
    eval_series = int(os.environ.get("EVAL_SERIES", "600"))


settings = Settings()
settings.artifacts_dir.mkdir(parents=True, exist_ok=True)

# Must match backend/inventory/taxonomy.py FRESH_SLUGS
FRESH_SLUGS = ["vegetables", "fruits", "meat-seafood", "dairy", "bakery", "prepared-deli", "frozen", "sweets"]
