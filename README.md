# FoodBridge – AI-Powered Food Waste Management Platform

Surplus identification and redistribution optimization, implemented through **Weeks 1–6** of the project plan:

| Layer | Tech | Where |
|---|---|---|
| Core API (multi-tenant) | Django 5/6 + DRF, JWT, drf-spectacular (Swagger) | `backend/` |
| Waste prediction microservice | FastAPI, Prophet, PyTorch LSTM, APScheduler | `ml_service/` |
| Web + mobile app | Flutter (one codebase → Chrome/web, Android, iOS) | `frontend/` |
| Dataset | [FreshRetailNet-50K](https://huggingface.co/datasets/Dingdong-Inc/FreshRetailNet-50K) | `scripts/fetch_dataset.py`, `data/` |
| Deployment | Docker, docker-compose, Render blueprint | `*/Dockerfile`, `docker-compose.yml`, `render.yaml` |

```
 Flutter app (web / Android / iOS)
        │  REST + JWT
        ▼
 Django API ──────────────── PostgreSQL / SQLite
   │  inventory, expiry engine, taxonomy, POS REST, marketplace, matching, pickups, analytics
   │  ▲  /internal/inventory-snapshot   /internal/risk-scores   (X-Service-Key)
   ▼  │
 FastAPI ML service  ── Prophet (per category) + LSTM (global) → ensemble forecast
      waste-risk scoring · smart reorder · batch job every 6 h · real-time endpoints
```

---

## 1. Quick start (local, no Docker)

Requirements: Python 3.11+, Flutter 3.22+ (for the app).

```bash
# 0) dataset → data/freshretailnet/{train,eval}.parquet
python scripts/fetch_dataset.py            # downloads FreshRetailNet-50K from Hugging Face
# python scripts/fetch_dataset.py --synthetic   # offline, schema-identical sample

# 1) Django API  (http://localhost:8000, Swagger at /api/docs/)
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo                 # demo businesses, NGOs, stock, pickups, dataset stores
python manage.py runserver 8000

# 2) ML service  (http://localhost:8001, Swagger at /docs)      – new terminal
cd ml_service
pip install -r requirements.txt
python scripts/train.py                    # trains Prophet + LSTM, writes artifacts/ + metrics.json
uvicorn app.main:app --port 8001

# 3) Background jobs (expiry alerts, pickup reminders, risk refresh) – new terminal
cd backend && python manage.py run_scheduler

# 4) Flutter app – new terminal
cd frontend
./setup_platforms.sh                       # generates android/ ios/ folders + camera permissions
flutter run -d chrome                      # web
flutter run -d emulator-5554 --dart-define=API_BASE_URL=http://10.0.2.2:8000/api   # Android emulator
flutter run -d <iphone> --dart-define=API_BASE_URL=http://<your-LAN-IP>:8000/api    # physical device
```

The repo ships a pre-seeded `backend/db.sqlite3` and trained `ml_service/artifacts/`, so steps 0, `seed_demo`
and `train.py` can be skipped for a first look.

### Demo accounts

| Role | Email | Password |
|---|---|---|
| Platform admin | admin@foodbridge.dev | Admin@12345 |
| Business (hotel) | hotel@foodbridge.dev | Demo@12345 |
| Business (bakery / spice store / canteen) | bakery@ · spice@ · canteen@foodbridge.dev | Demo@12345 |
| Dataset-backed supermarkets | store4@ · store5@ · store6@foodbridge.dev | Demo@12345 |
| NGOs | hope@ · annapoorna@ · greenhands@ · seva@ · cityrelief@foodbridge.dev | Demo@12345 |

The login screen has one-tap chips for these.

### API documentation
* Django (110 operations): **http://localhost:8000/api/docs/** (Swagger UI), `/api/redoc/`, `/api/schema/`
* ML service: **http://localhost:8001/docs**

Authorize in Swagger with `POST /api/auth/login/` → paste `access` as `Bearer <token>`.

---

## 2. Docker / cloud deployment

```bash
cp .env.example .env          # set secrets
docker compose up --build
# web app  http://localhost:8080   API  http://localhost:8000/api/docs/   ML  http://localhost:8001/docs
```

Services: `db` (Postgres 16), `redis` (shared cache), `backend` (gunicorn, migrates + seeds on first boot), `scheduler`
(`run_scheduler`), `ml` (uvicorn; its own 6-hourly batch job), `web` (Flutter web build on nginx with SPA routing).

**Free cloud deployment (no credit card):** Render (API + Postgres) · Hugging Face Spaces (ML service) ·
Vercel (Flutter web/PWA) · GitHub Actions (scheduled jobs). Step-by-step guide: **[docs/DEPLOY_FREE.md](docs/DEPLOY_FREE.md)**
(`render.yaml`, `deploy/deploy_hf_space.py`, `frontend/web/vercel.json`, `.github/workflows/scheduled-jobs.yml`).
The same Docker images also run on any VM with `docker compose`.

**Mobile release builds:** `flutter build apk --release --dart-define=API_BASE_URL=https://<api-host>/api`
(and `flutter build ipa` on macOS).

---

## 3. Feature map (PDF requirement → implementation)

### Weeks 1–2 · Django core
| Requirement | Implementation |
|---|---|
| Inventory input – manual | `POST /api/inventory/products/`, `POST /api/inventory/batches/`, `/batches/{id}/adjust/` · app: *Inventory → Receive stock* |
| Inventory input – CSV bulk upload | `POST /api/inventory/upload-csv/` (modes `inventory` / `transactions`, per-row error report, upload history), `GET /api/inventory/csv-template/` · app: *CSV upload* dialog |
| Inventory input – POS REST | `POST /api/pos/v1/sales/`, `/pos/v1/receipts/`, `GET /pos/v1/products/` with `X-POS-Key`; keys managed at `/api/pos/integrations/` (create / rotate / disable) · app: *Settings → POS integrations* |
| Expiry tracking + automated alerts | `inventory/services.py::run_expiry_scan` (warning / critical / expired, per-category or per-org thresholds `/api/expiry/thresholds/`), alerts at `/api/expiry/alerts/`, e-mail + in-app notifications, hourly + 06:00 job in `run_scheduler` · app: *Expiry alerts* |
| Food taxonomy (perishability, storage) | `inventory/taxonomy.py` – 15 categories aligned to FreshRetailNet `first_category_id`, perishability, storage mode/temperature, shelf life, CO₂e factor, keyword classifier (`POST /api/taxonomy/categories/classify/`); products are auto-categorised |
| Barcode / QR scanning (mobile-friendly) | `GET /api/inventory/products/by-barcode/{code}/`, `POST /api/inventory/scan/` (receive / sell / waste, creates unknown products) · app: *Scan* – camera via `mobile_scanner` on Android, iOS and browsers + manual entry |
| Multi-tenant DB (inventory, transactions, donation logs) | Every row is scoped to an `Organization` (`core/mixins.py::TenantScopedMixin`); models `Product`, `InventoryBatch`, `StockTransaction`, `SurplusListing`, `Pickup` (donation log), `Notification` |

### Weeks 3–4 · Waste prediction engine
| Requirement | Implementation |
|---|---|
| Time-series preprocessing | `ml_service/app/data.py` – daily aggregation, **stock-out correction** from `hours_stock_status` (latent demand), calendar / weather / promo features, category aggregation, train/eval split exactly as the dataset |
| Prophet demand model | `ml_service/app/models/prophet_model.py` – one model per food category with holiday / discount / weather regressors; product forecasts are scaled by product share |
| LSTM demand model | `ml_service/app/models/lstm_model.py` – global PyTorch LSTM over 28-day windows with exogenous features and product/category embeddings, Huber loss, per-series scaling |
| Daily & weekly forecasts | `POST /forecast`, `/forecast/category/{id}` → daily values, 80 % band, weekly totals; ensemble weights = inverse WAPE · Django proxy `GET /api/predictions/forecast/{product_id}/` · app: *Predictions → forecast* |
| Waste risk score (days-to-expiry + stock + forecast) | `ml_service/app/risk.py` – 0–100 score = 45 % expected unsold share + 25 % expiry urgency (perishability-specific decay) + 15 % stock cover + 15 % waste probability; FIFO demand sharing across batches; recommended action (discount % or donate) |
| Smart reorder (forecast + storage capacity) | `ml_service/app/reorder.py` – order-up-to over lead time + review period, safety stock by perishability, shelf-life cap, proportional scaling to free storage capacity, comparison against naive ordering · `/api/predictions/reorder/` |
| FastAPI microservice – scheduled batch + real-time | `ml_service/app/main.py` (`/risk/score`, `/risk/score/batch`, `/reorder/recommend`, `/batch/run`, `/batch/runs`, `/train`, `/models`) and `app/scheduler.py` (APScheduler, every `BATCH_EVERY_HOURS`, pulls `/internal/inventory-snapshot/`, pushes `/internal/risk-scores/`). Django falls back to a heuristic when the service is offline |

Training report (`ml_service/artifacts/metrics.json`, official eval split, 7-day horizon, 400 series):

| Model | WAPE | MAE | RMSE |
|---|---|---|---|
| Seasonal naive | 26.6 % | 0.321 | 0.432 |
| **Prophet** | **24.3 %** | 0.294 | 0.394 |
| LSTM | 24.8 % | 0.299 | 0.399 |
| Ensemble | 24.5 % | 0.295 | 0.395 |

> These numbers were produced in the build sandbox, where huggingface.co was unreachable, on the
> schema-identical synthetic sample (`fetch_dataset.py --synthetic`). Run `python scripts/fetch_dataset.py`
> and `python ml_service/scripts/train.py` to reproduce on the real FreshRetailNet-50K data.

### Weeks 5–6 · Flutter redistribution app (web + mobile)
| Requirement | Implementation |
|---|---|
| Surplus listing portal (qty, expiry, pickup location, availability windows) | `/api/marketplace/listings/` (+ `from-batch/`, `suggestions/` from high-risk batches) · app: *Surplus listings*, *New listing* (multiple windows, dietary tags, cold-chain flag) |
| AI matching (food type, quantity, proximity) | `marketplace/matching.py` – hard constraints (category, distance, refrigeration, capacity, dietary) then weighted score: food-type fit, haversine proximity, quantity fit, TF-IDF needs similarity, pickup history, reliability, timing; weights shift toward proximity as expiry nears. `/listings/{id}/matches/`, NGO live feed `/listings/feed/` · app: match cards with score breakdown, NGO *Live donations* (auto-refresh) |
| Pickup scheduling – calendar + confirmation notifications | `/api/pickups/` claim/offer → both-side confirm → collect → complete, reschedule, cancel / no-show, `/pickups/calendar/`, reminder job 2 h before; in-app + e-mail notifications · app: *Pickup schedule* (table_calendar) + detail timeline |
| Business dashboard (inventory health, waste risk charts, donation tracker) | `/api/analytics/business/` · app: business *Dashboard* |
| NGO dashboard (incoming donations, pickup history, beneficiary impact) | `/api/analytics/ngo/` · app: NGO *Dashboard*, *Our needs* |
| Sustainability impact (food diverted, CO₂e, meals) | `/api/analytics/impact/?scope=mine|platform` – kg diverted, CO₂e via category factors, meals (0.42 kg/meal), car-km & tree equivalents · app: *Impact tracker* |
| Sample dashboard from the PDF | admin *Dashboard* (`/api/analytics/admin/`): KPI cards Listings Active / Food Rescued / CO₂ Prevented / NGOs Active, *Food Rescued by Category (kg — Last 30 Days)*, *Top Donor Partners*, *Recent Rescue Operations* (LST-xxxx, status chips) |
| Cloud deployment | Section 2 |

App structure (`frontend/lib`): `api/` HTTP client with JWT refresh · `state/` auth · `router.dart` role-guarded
routes · `widgets/` shell (green top bar + sidebar on desktop, drawer + bottom navigation on phones), cards,
charts (fl_chart) · `screens/business|ngo|shared|admin`.

---

## 4. Weeks 7–8 – testing, performance, UX, PWA

Full write-up with every defect found, before/after numbers and known limitations:
**[docs/TESTING_REPORT.md](docs/TESTING_REPORT.md)**.

```bash
# automated tests
cd backend && python manage.py test tests          # 61 Django tests incl. full cross-module pipeline (real ML in-process)
cd ml_service && python -m pytest tests            # 16 ML service tests
python tests/e2e_flow.py                           # 25 live checks against running servers (8000 + 8001)

# performance
python tests/load/profile_queries.py               # SQL queries per endpoint (N+1 detector)
python tests/load/load_test.py --stages 5,10,25,50,100
locust -f tests/load/locustfile.py --host http://localhost:8000

# browsers (Playwright): PWA audit + cross-browser app smoke test
python tests/browser/pwa_check.py --self-test                       # or --url http://localhost:8080
python -m playwright install chromium firefox webkit
python tests/browser/app_smoke.py --url http://localhost:8080 --browsers chromium,firefox,webkit
```
`e2e_flow.py` writes test data; re-seed afterwards with `rm backend/db.sqlite3 && python manage.py migrate && python manage.py seed_demo`.

**Installable app (PWA):** `flutter build web --release --no-web-resources-cdn`, serve `build/web` over HTTPS
(or localhost) and Chrome/Edge/Android offer *Install*; on iPhone use *Share → Add to Home Screen*. The app shell
works offline and shows the last loaded data; logging out clears the offline data.

## 5. Notes
* Local dev uses SQLite; set `POSTGRES_DB/USER/PASSWORD/HOST` for Postgres (compose does this).
* E-mail notifications print to the console by default; set `EMAIL_BACKEND` + SMTP variables in `.env`.
* Browser camera scanning needs HTTPS (or `localhost`).
* The Flutter sources were written and reviewed without a Flutter SDK in the build sandbox (no network access to
  Google storage), so the first `flutter pub get` / `flutter run` is also the first compile — if the analyzer flags
  anything, it will be a small fix.
