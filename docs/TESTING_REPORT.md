# FoodBridge – Weeks 7–8 Testing & Refinement Report

Covers the first three Weeks 7–8 deliverables: (1) end-to-end integration testing and cross-module fixes,
(2) load / stress testing, cross-browser validation and performance work, (3) UX refinement
(clarity, contextual help, mobile & tablet responsiveness) — plus the Progressive Web App.

Environment for all numbers below: build sandbox, **1 vCPU**, SQLite (WAL), gunicorn 4 workers × 2 threads,
ML service on the same machine. Production (Postgres, more cores) will be faster; the *relative*
improvements and the absence of errors are what matter here.

---

## 1. Integration testing across all modules

### Test suites

| Suite | Command | Tests | Result |
|---|---|---|---|
| Django (unit + API + cross-module) | `cd backend && python manage.py test tests` | 61 | ✅ all pass |
| ML service (FastAPI contract, edge cases, invariants) | `cd ml_service && python -m pytest tests` | 16 | ✅ all pass |
| Live end-to-end smoke (both servers running) | `python tests/e2e_flow.py` | 25 checks | ✅ 25/25 |
| PWA audit in Chromium | `python tests/browser/pwa_check.py --self-test` | 20 checks | ✅ 20/20 |

`backend/tests/`:

| File | What it covers |
|---|---|
| `test_inventory.py` | manual entry + auto-classification, tenant-scoped products, FIFO consumption, CSV (per-row errors, `;` delimiter, Windows-1252, date formats, expiry < received, transactions mode, empty/header-only files), barcode scan (unknown / create / sell), POS key auth, idempotent POS sales, disabled keys, expiry levels + idempotency, threshold overrides, acknowledging alerts, taxonomy classifier |
| `test_tenancy.py` | cross-tenant reads/writes (404/403), role permissions, anonymous access, service-key-only internal endpoints, private notifications, JWT login |
| `test_predictions.py` | ML-offline fallback (risk, reorder, forecast, model status), **real FastAPI + trained Prophet/LSTM in-process** for risk refresh / reorder / forecast, scheduled-batch snapshot → ingest contract |
| `test_marketplace.py` | listing validation, from-batch rules, distance / cold-chain / dietary hard constraints, ranking, explained score breakdown, feed + decline, match notifications, full pickup lifecycle with stock deduction + impact + e-mails, donor offers, claim / confirm / complete / cancel edge cases, outsider access, reschedule, withdrawal, no-show reliability, reminders, calendar |
| `test_integration_pipeline.py` | **one test through every module**: CSV history + stock → POS sale → scan → expiry engine → ML risk scoring → AI suggestion → listing from batch → matching → NGO feed → claim/confirm/collect/deliver → business, NGO, impact and admin dashboards must agree; empty-org dashboards; orgs without coordinates; cache invalidation |

### Defects found and fixed

| # | Module | Problem found by the tests | Fix |
|---|---|---|---|
| 1 | Inventory (security) | A business could create a batch on **another tenant's product** by sending its id | Tenant-scoped primary-key field `OrgScopedPrimaryKey` + explicit check |
| 2 | All (dates) | `date.today()` used the server clock (UTC in Docker) while the app runs in Asia/Kolkata → days-to-expiry off by one between 00:00–05:30 IST | `timezone.localdate()` everywhere |
| 3 | CSV → marketplace → impact | Product attributes in a later CSV (unit, kg per unit) were ignored when the product already existed → **donated kg and CO₂e wrong** | Upsert of explicit master data in `get_or_create_product` |
| 4 | Marketplace | Claim without a slot → 500 | 400 with a clear message |
| 5 | Marketplace | Claim could use **another listing's** availability window | Window must belong to the listing |
| 6 | Marketplace | Same NGO could open several pickups on one listing | Rejected |
| 7 | Marketplace | Pickups could be booked in the past or **after the best-before date**; listings could offer windows after it | Validated on claim, offer, reschedule and listing create |
| 8 | Marketplace | Confirming twice silently reset the timestamp | 400 "already confirmed" |
| 9 | Marketplace | Received kg could exceed collected kg; the failed completion still marked the pickup collected | Validation runs before any side effect |
| 10 | Marketplace | Expired / empty / already-listed batches could be listed again | Rejected in `listing_from_batch` |
| 11 | Matching | NGOs **without refrigeration** were matched to chilled food when they had a vehicle | Cold chain is now a hard constraint |
| 12 | Predictions | Forecast for another tenant's product → 500; non-numeric `horizon` → 500 | 404 / 400 |
| 13 | Predictions ↔ ML | Scheduler run id that isn't numeric → 500 | Tolerated |
| 14 | ML service | Batch with zero stock still scored ≈11 risk | Scores 0 / "No stock on hand" |
| 15 | Inventory | Adjusting a depleted batch recorded 0-quantity transactions | 400 |
| 16 | Inventory | CSV sales rows with quantity 0 accepted; no upload size limit | Validated; 5 MB limit |
| 17 | Feed | Non-numeric `min_score` / `max_distance_km` → 500 | 400 |

## 2. Load, stress and cross-browser testing

### Tools
* `tests/load/profile_queries.py` – SQL query count + server time for every endpoint and role (N+1 detector).
* `tests/load/load_test.py` – async load generator with the real traffic mix (60 % business, 35 % NGO,
  5 % admin; dashboards, lists, live-feed polling, scans). Ramps concurrency in stages.
* `tests/load/locustfile.py` – the same scenario for Locust (web UI with live charts).

### Bottlenecks found and fixed
| Finding | Evidence | Fix |
|---|---|---|
| N+1 queries on listings | `/marketplace/listings/` = **50 queries**, 36.6 ms | Correlated sub-query annotations → **4 queries**, 14.6 ms |
| `database is locked` 500s under concurrent scans | 4/12 parallel scans failed | SQLite WAL + `IMMEDIATE` transactions + 20 s busy timeout; unique `(organization, barcode)` + race-safe create → 12/12 OK |
| Dashboards recomputed on every poll | business dashboard = 20 queries per call | Versioned cache: writes bump the org's version via signals, so data is never stale in the same worker; `REDIS_URL` shares it across workers |
| No protection against abusive clients | – | DRF throttling (anon 120/min, user 1200/min, login 20/min, POS 600/min – all env-tunable), GZip |
| Errors not visible in production logs | 500s produced no traceback | Logging config keeps Django's loggers |

### Results (stress: zero think time)

| Concurrent users | Before: req/s | Before: p95 | After: req/s | After: p95 | Errors after |
|---|---|---|---|---|---|
| 5 | 75.8 | 133 ms | **99.3** | **77 ms** | 0 % |
| 10 | 75.3 | 186 ms | **97.3** | **149 ms** | 0 % |
| 25 | 85.7 | 353 ms | **111.4** | **282 ms** | 0 % |
| 50 | 74.5 | 1 251 ms | **100.2** | **1 048 ms** | 0 % |
| 100 | – | – | 89.3 | 1 852 ms | 0 % |

Realistic load (100 users, 0–4 s think time): **42 req/s, median 26 ms, p95 479 ms, 0 errors**.
Beyond ~110 req/s the single CPU is saturated (latency grows linearly, no errors) – scale with more
gunicorn workers/cores, Postgres and Redis (`docker-compose.yml` / `render.yaml`).

Reproduce:
```bash
cd backend && THROTTLE_USER=1000000/min THROTTLE_LOGIN=1000/min gunicorn config.wsgi -w 4 --threads 2 -b :8000
python tests/load/load_test.py --stages 5,10,25,50,100 --seconds 20
locust -f tests/load/locustfile.py --host http://localhost:8000      # UI on :8089
```

### Cross-browser validation
* **Automated PWA audit** (`tests/browser/pwa_check.py`) – Chromium run in the sandbox: 20/20
  (manifest, icon sizes, installability via Chrome DevTools, service worker, offline shell, offline deep
  links, offline API cache, cache cleared on logout, no horizontal overflow at 360/768/1440 px).
* **App smoke test** (`tests/browser/app_smoke.py`) – logs in as business, NGO and admin in
  **Chromium, Firefox and WebKit (Safari engine)** at phone/tablet/desktop sizes through Flutter's
  accessibility tree, opens key pages and saves screenshots. Needs the compiled app (Flutter SDK), so it
  has to be run on your machine:
  `python -m playwright install chromium firefox webkit && python tests/browser/app_smoke.py --url http://localhost:8080`
* Manual checklist (tick per browser – Chrome, Edge, Firefox, Safari macOS, Safari iOS, Chrome Android):
  login · dashboard charts render · CSV upload file picker · camera scanner permission prompt ·
  date/time pickers · calendar swipe · dialogs full-screen on phone · install prompt / Add to Home Screen ·
  offline banner when the API stops · update prompt after redeploy.

## 3. UX refinement

| Area | Change |
|---|---|
| Responsiveness | New **tablet layout** (640–999 px) with a navigation rail; desktop keeps the sidebar, phones the drawer + bottom bar |
| Phones | Data tables turn into **stacked cards** below 560 px (no sideways scrolling); form dialogs open **full-screen** with actions pinned at the bottom |
| Contextual help | Help (?) tooltips on every main page and on the key dashboard numbers (value at risk, high-risk batches, CO₂e, matched donations …); larger tap targets; screen-reader labels |
| Onboarding | Dismissible **"Getting started"** panel per role with the 3–4 steps of the workflow, each linking to its screen |
| Clarity of errors | Offline banner while the API is unreachable; friendly messages for network loss and HTTP 429; every validation error from section 1 now reaches the user as readable text |
| Accessibility | Tooltips on all icon-only buttons, semantics on KPI cards and help icons, text scaling respected up to 135 % without breaking layouts |

## 4. Progressive Web App

* `web/manifest.json` – name, standalone display, theme colours, 192/512 icons **incl. maskable**, app
  shortcuts (Scan, Live donations, Pickups), install-sheet screenshots.
* `web/sw.js` – precached app shell, stale-while-revalidate for assets & fonts, network-first page
  navigations with offline fallback to the app (deep links work offline and on hosts without SPA rewrites),
  network-first **API GET cache** so the last loaded data is shown offline (cleared on logout, never caches
  auth/POS/internal endpoints or writes), versioned caches.
* `web/index.html` – install banner (Chrome/Edge/Android), "Add to Home Screen" hint on iOS, "new version
  available → Reload" prompt, hourly update check.
* `web/flutter_bootstrap.js` – disables Flutter's default service worker so the two don't conflict.
* `web/offline.html`, iOS meta tags + apple-touch-icon; nginx serves `sw.js` / `manifest.json` uncached.
* Build with `flutter build web --release --no-web-resources-cdn` (CanvasKit bundled → works offline).

## Known limitations
* Flutter code has not been compiled in the build sandbox (no Flutter SDK); run `flutter analyze` first.
* Only Chromium was available here – Firefox/WebKit runs of the browser tests are for your machine.
* Load numbers are from 1 vCPU + SQLite; re-run against the deployed Postgres setup for final figures.
* With the default per-process cache, a different gunicorn worker may show a dashboard up to 30 s old;
  set `REDIS_URL` (compose already has Redis) to remove that.
* Model metrics are from the synthetic FreshRetailNet-schema sample; retrain on the real dataset.
