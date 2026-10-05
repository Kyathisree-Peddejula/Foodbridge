# Free cloud deployment (no credit card)

| Part | Free host | What you get |
|---|---|---|
| Django API + PostgreSQL | **Render** (free web service + free Postgres) | `https://foodbridge-api.onrender.com` |
| ML service (Prophet + LSTM, FastAPI) | **Hugging Face Spaces** (free Docker Space, 2 vCPU / 16 GB) | `https://<hf-user>-foodbridge-ml.hf.space` |
| Flutter web app / PWA | **Vercel** (free) | `https://<project>.vercel.app` |
| Background jobs (expiry scans, reminders, risk scoring) | **GitHub Actions** cron (free) | runs every 10 min |

Total time: about 45–60 minutes, most of it waiting for builds.

---

## 0. Push the latest code
Copy the new files over your project, then in VS Code's terminal (project root):
```bash
git add -A
git commit -m "Free-tier deployment config"
git push
```

## 1. Backend on Render (≈15 min)
1. Go to <https://render.com> → **Get Started** → sign up **with GitHub**.
2. **New +** → **Blueprint** → choose your FoodBridge repository → **Connect**.
   Render reads `render.yaml` and shows *foodbridge-db* (free Postgres) and *foodbridge-api* (free web service).
3. It asks for the two `sync: false` values – leave **ML_SERVICE_URL** and **CSRF_TRUSTED_ORIGINS** empty for now → **Apply**.
4. Wait for the build (first time 8–15 min). The service goes **Live**; the first start also creates the demo data.
5. Open your service → copy its URL, e.g. `https://foodbridge-api.onrender.com`, and check:
   * `https://foodbridge-api.onrender.com/api/health/` → `{"status": "ok", …}`
   * `https://foodbridge-api.onrender.com/api/docs/` → Swagger UI
6. **Environment** tab → copy the value of **SERVICE_API_KEY** (click the eye icon). You need it in steps 2 and 4.

> If your service name was taken, Render adds a suffix (e.g. `foodbridge-api-x1y2.onrender.com`) – always use the URL Render shows you.

## 2. ML service on Hugging Face Spaces (≈15 min)
1. Create an account at <https://huggingface.co/join>.
2. <https://huggingface.co/settings/tokens> → **Create new token** → type **Write** → copy it.
3. In VS Code's terminal (venv active, project root):
   ```bash
   pip install huggingface_hub
   huggingface-cli login            # newer versions: hf auth login   → paste the token
   python deploy/deploy_hf_space.py --space <your-hf-username>/foodbridge-ml --django-url https://foodbridge-api.onrender.com/api --service-key <SERVICE_API_KEY>
   ```
4. Open `https://huggingface.co/spaces/<your-hf-username>/foodbridge-ml` – the status goes *Building* → *Running* (5–10 min).
5. Check `https://<your-hf-username>-foodbridge-ml.hf.space/health` → `"models_ready": true`, and `/docs` for Swagger.

## 3. Connect the API to the ML service (2 min)
Render → *foodbridge-api* → **Environment** → set
`ML_SERVICE_URL = https://<your-hf-username>-foodbridge-ml.hf.space` → **Save changes** (it redeploys automatically).

## 4. Scheduled jobs on GitHub Actions (3 min)
GitHub → your repo → **Settings → Secrets and variables → Actions → New repository secret**, add:

| Name | Value |
|---|---|
| `FOODBRIDGE_API_URL` | `https://foodbridge-api.onrender.com/api` |
| `SERVICE_API_KEY` | the key from step 1.6 |
| `ML_URL` | `https://<your-hf-username>-foodbridge-ml.hf.space` |

Then **Actions** tab → enable workflows if asked → **FoodBridge scheduled jobs** → **Run workflow**.
The log should end with `{"jobs": {"expiry_scan": "ok", "pickups": "ok", "risk_scoring": "ok"}, …}`.
From now on it runs every 10 minutes (this also stops the free services from going to sleep).

## 5. Frontend on Vercel (≈10 min)
Vercel's build servers don't have Flutter, so build on your PC and upload the result:
```bash
cd frontend
flutter build web --release --no-web-resources-cdn --dart-define=API_BASE_URL=https://foodbridge-api.onrender.com/api --dart-define=ML_DOCS_URL=https://<your-hf-username>-foodbridge-ml.hf.space/docs
```
(If `--no-web-resources-cdn` is rejected by your Flutter version, run it without that flag.)

Install the Vercel CLI once (needs Node.js from <https://nodejs.org>) and deploy the built folder:
```bash
npm install -g vercel
cd build/web
vercel login                 # choose "Continue with GitHub"
vercel --prod
```
Answer the prompts: *Set up and deploy?* **Y** → your account → *Link to existing project?* **N** →
name **foodbridge** → directory **./** → *Modify settings?* **N**.
It prints the production URL, e.g. `https://foodbridge.vercel.app`. `vercel.json` (copied from `web/`) makes
links like `/pickups` work and keeps the PWA updating correctly.

Optional: Render → Environment → `CSRF_TRUSTED_ORIGINS = https://foodbridge.vercel.app` (only for the Django admin).

**Redeploying the frontend later:** run the same `flutter build web …` command, then `cd build/web && vercel --prod`.

## 6. Check everything
- [ ] Open the Vercel URL → log in with `hotel@foodbridge.dev / Demo@12345` (first request may take ~1 min if the API was asleep).
- [ ] Predictions → Model performance shows **online** (ML service connected).
- [ ] Predictions → Waste risk → **Score now** reports engine `ml-service`.
- [ ] NGO login `hope@foodbridge.dev` → Live donations shows listings.
- [ ] On your phone: open the Vercel URL → *Install* / *Add to Home Screen*; the Scan page can use the camera (HTTPS).
- [ ] Re-run the load test against the cloud for your report:
      `python tests/load/load_test.py --base https://foodbridge-api.onrender.com/api --stages 5,10,25 --seconds 20`
      (expect lower numbers than locally - the free instance has a small shared CPU).

## Free-tier limits and fixes
| Situation | What happens / what to do |
|---|---|
| API asleep (no traffic for 15 min, e.g. Actions disabled) | First request takes 30–60 s, then normal. The GitHub workflow prevents this. |
| Render free Postgres | Free databases are deleted after roughly 30 days (check Render's current policy). For a database that does not expire, create a free one at <https://neon.tech>, copy its connection string and set it as `DATABASE_URL` on Render (replaces the Render database). |
| HF Space sleeps | After ~48 h without traffic; the workflow pings it. If asleep, Django automatically falls back to heuristic forecasts until it wakes. |
| "Cannot reach the server" in the app | Check the `API_BASE_URL` you built with (must be `https://…/api`), then rebuild and redeploy the frontend. |
| Login works locally but not on Vercel | The URL must be **https**; CORS is open by default (`CORS_ALLOW_ALL=true`). |
| Render build fails | Render → *Events/Logs*; send me the last 30 lines. |
| GitHub scheduled runs stop | GitHub pauses scheduled workflows after 60 days without repository activity – push any commit or re-enable. |
