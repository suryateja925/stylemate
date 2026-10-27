# StyleMate AI

StyleMate AI is a plan-aware personal stylist MVP. It accepts real wardrobe photos, asks a configured vision provider to identify visible garments, stores only user-confirmed items, and generates daily multi-event outfit recommendations from those saved items.

## What works

- Supabase Auth sessions in production; development-only local profiles are isolated to the local environment.
- PostgreSQL production persistence managed by Alembic migrations; SQLite schema creation remains development-only.
- Private Supabase Storage for wardrobe images, with short-lived signed image URLs.
- Per-account database-backed limits for AI scans, chat, voice commands, and shopping searches.
- Secure image upload validation and server-generated media paths.
- Gemini and OpenAI vision-provider adapters with structured JSON validation.
- Occlusion-aware scan states, additional scan photos, editable detections, rectangular garment crops, and explicit confirmation.
- Persistent wardrobe with availability and laundry controls (SQLite locally, PostgreSQL in production).
- Multi-event daily plans, deterministic wardrobe-only recommendations, alternatives, replacement, saving, and explicit worn history.
- Style preferences, progress statistics, responsive frontend navigation, and empty/loading/error states.
- Optional weather-provider interface; recommendations never claim weather when no provider is configured.
- Dashboard voice assistant with browser microphone permission, continuous utterance handling, pause/resume/stop, spoken responses, and a text-command fallback.
- Server-side AI tool selection limited to registered wardrobe, schedule, outfit, preparation, preference, scanner-navigation, and shopping-search actions.
- Vercel static deployment configuration, Render API blueprint, strict production configuration validation, and browser security headers.

## Requirements

- Python 3.11+ (tested with Python 3.14 in this workspace)
- Node.js 20+ and npm
- A verified image-capable Gemini or OpenAI API model for real scan analysis. The app starts without credentials but scanner analysis reports a useful configuration error.

## Production deployment: Vercel + Render + Supabase

1. Create a Supabase project. Configure Auth's site URL and redirect allowlist for the Vercel domain. Enable email confirmation and configure SMTP before public signup.
2. In the Supabase SQL Editor, run [`backend/scripts/setup_supabase_storage.sql`](backend/scripts/setup_supabase_storage.sql). It creates the private `wardrobe-private` bucket; do not make this bucket public.
3. Use the Supabase PostgreSQL **session pooler** connection string for the Render `DATABASE_URL`, with `sslmode=require`. Render runs `alembic upgrade head` during each build. Use a new/empty production database; existing databases require a reviewed baseline/stamp procedure before deployment.
4. Create a Render Blueprint from [`render.yaml`](render.yaml). Configure the prompted `DATABASE_URL`, `FRONTEND_ORIGINS`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and `SUPABASE_SECRET_KEY` values. Keep the secret key only in Render; never add it to Vercel or frontend variables. Set `FRONTEND_ORIGINS` to the exact HTTPS Vercel origin. The configured API host is `stylemate-api.onrender.com`; update `ALLOWED_HOSTS` if you use a custom domain.
5. Create a Vercel project with the frontend directory as its root. Set `VITE_API_URL=https://stylemate-api.onrender.com`, `VITE_SUPABASE_URL`, and `VITE_SUPABASE_PUBLISHABLE_KEY`, then deploy. Update the CSP API hostname in [`frontend/vercel.json`](frontend/vercel.json) if you use a custom Render domain.
6. Configure a verified image-capable AI provider in Render before enabling real scanner use. Optional AI provider variables can remain unset, but chat/voice/scanner AI features then return configuration errors.
7. Verify `https://stylemate-api.onrender.com/health`, account creation/sign-in, an authenticated API request, private photo upload/view, and an Alembic migration before inviting users.

The API refuses to start in production unless it has PostgreSQL, explicit HTTPS CORS origins, Supabase Auth, and private Supabase Storage configuration. Alembic enables Row Level Security on every application table without adding browser-access policies: only the API's database role can access application rows. `/health` is intentionally public for the Render monitor; application APIs require a verified Supabase access token. Signed photo URLs expire after one hour. The Render Blueprint also runs a separate reminder worker; it retries database errors and creates in-app notifications, not email, push, or OS notifications. Supabase backups/point-in-time recovery depend on the selected project plan and must be enabled and restore-tested separately.

The current default abuse limits are 8 scan/photo-analysis calls per account per 10 minutes, 30 chat calls per minute, 20 voice calls per minute, and 30 shopping searches per minute. Rate-limit counters are shared through PostgreSQL and return `429` with `Retry-After`.

The Vercel frontend uses the Supabase browser client and bearer tokens, with sign-up, sign-in, password recovery, sign-out, and account/data deletion flows. Configure Supabase Auth's production site URL and redirect allowlist exactly; do not disable email confirmation or expose service-role credentials. Set database backups, restore procedures, billing alerts, and provider usage limits before public launch. No production service can be provisioned from this repository alone; deployment accounts, project keys, domain ownership, and SMTP configuration must be supplied by the owner.

## Windows PowerShell setup

```powershell
cd C:\Users\DELL
New-Item -ItemType Directory -Force stylemate-ai | Out-Null
cd .\stylemate-ai
Copy-Item .env.example .env
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r backend\requirements.txt
Set-Location frontend
npm install
Set-Location ..
```

Edit `.env` and set `AI_PROVIDER` plus the matching API key and verified model ID before using the scanner. Never put these values in frontend code. For local work, the API uses development-only `X-User-Id` profiles and SQLite/local media. Production deployments must use the Supabase configuration above; the app does not fall back to local identity when built for production.

Vite proxies local API and media requests to `http://localhost:8000`. If you run the API elsewhere, copy `frontend/.env.example` to `frontend/.env` and set `VITE_API_URL` to the backend origin. This variable is only a URL; AI keys remain server-side.

Start the backend in one terminal:

```powershell
cd C:\Users\DELL\stylemate-ai
.\.venv\Scripts\Activate.ps1
python -m uvicorn backend.app.main:app --reload --port 8000
```

Start the frontend in another (from the `frontend` directory):

```powershell
cd C:\Users\DELL\stylemate-ai\frontend
npm run dev
```

Open http://localhost:5173. API documentation is available at http://localhost:8000/docs in development (disabled in production).

## Checks

```powershell
cd C:\Users\DELL\stylemate-ai
.\.venv\Scripts\Activate.ps1
python -m pytest backend\tests -q
Set-Location frontend
npm run build
npm run test
npm audit
Set-Location ..
```

The backend creates the local SQLite schema automatically on startup. You can also initialize it explicitly:

```powershell
python -m backend.scripts.init_db
```

Local development uses SQLAlchemy `create_all` plus a small additive SQLite compatibility migration. Production schema changes are managed with Alembic. Generate migrations with `python -m alembic revision --autogenerate -m "describe change"` and review the generated migration before applying it. Production deploys run `python -m alembic upgrade head`; do not run development `create_all` against production. For a clean local reset, stop the server and remove `stylemate.db`; uploaded media is retained until manually deleted.

## API and data notes

All application routes are under `/api`. Local development may use `X-User-Id`; production rejects that header and verifies the Supabase bearer token's signature, issuer, audience, and expiry. Database queries are scoped to the verified user ID. All uploaded production images are stored in the private Supabase bucket and exposed only through expiring signed URLs.

The AI adapters request JSON describing only visible evidence. Bounding boxes use normalized coordinates: `x_min`, `y_min`, `x_max`, and `y_max` are each between 0 and 1. Crops are rectangular previews, not background-removed cutouts.

## Voice assistant

The dashboard's **Start Voice Assistant** button requests microphone permission only after a user gesture. While the dashboard is open and in the foreground, it processes successive speech utterances and resumes listening after a response. Pause, Resume, and Stop controls are available; leaving the dashboard, hiding the tab, stopping the session, or an unrecoverable speech-service error ends the active capture. Browser speech recognition is not guaranteed to work in background tabs, on locked phones, or after the app is closed.

Voice command understanding and registered tool selection use the same backend `AI_PROVIDER` and model/key settings as chat. No new API credential is required. The backend executes only allow-listed operations and scopes all data to the existing `X-User-Id`. Supported actions include searching confirmed wardrobe items, reading plans, outfit history, in-app reminders, and preparation tasks; creating or editing events when the date/event are clear; generating outfit recommendations; saving and giving feedback on the current recommendation; reading/updating explicit style preferences; opening the scanner; and preparing permitted shopping search links. Recent voice follow-ups are retained for 30 minutes to resolve clarification questions; command request IDs make retries idempotent. It does not purchase products, change/delete wardrobe items, access an external calendar, or schedule operating-system reminders. Camera/gallery scanning opens the existing scanner and still requires the user to choose and confirm an image.

Speech input/output use the browser's Web Speech APIs (speech recognition may use a browser-vendor service). Chromium-based Chrome and Edge desktop/Android builds are the primary targets; Firefox and Safari may not expose recognition and receive the text-command fallback. Support also varies by operating system, locale, and network. English (India) and Telugu recognition locales can be selected; available Telugu speech-synthesis voices depend on the device. Use HTTPS in deployments (localhost is allowed for development). Microphone permission is requested on Start, the temporary permission probe stream is released once recognition starts, and recognition is stopped on Pause, Stop, page hide, or navigation. This is not a background or always-on assistant: it cannot be relied on when the tab is backgrounded, the phone is locked, the app is closed, or the operating system suspends it.

The current weather interface includes a replaceable OpenWeather-compatible adapter contract but does not make network calls unless `WEATHER_PROVIDER` and `WEATHER_API_KEY` are set. Calendar access and OS reminder scheduling are intentionally not enabled by default; manual plans are the source of truth.
