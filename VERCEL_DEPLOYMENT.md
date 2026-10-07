# Deploy Mali Backend to Vercel

Mali is a FastAPI financial-intelligence API backed by Supabase Postgres, Firebase Authentication, AI providers, and SMTP email. It does not use MongoDB, loan reminders, or SMS services.

## Project configuration

- [main.py](main.py) exports `app` for Vercel's native FastAPI integration; `fast_api_app` remains available for local Uvicorn commands.
- [vercel.json](vercel.json) selects FastAPI, configures a 300-second function budget, and declares all five scheduled jobs. No `api/index.py`, custom build command, output directory, or `/server` prefix is needed.
- [api/routes/](api/routes/) contains the HTTP routers, [api/services/](api/services/) the business logic, and [api/templates/](api/templates/) the bundled email templates.
- [fetchers/](fetchers/), [ai/](ai/), [db/](db/), [firebase/](firebase/), and [tasks/](tasks/) must remain in the deployment.
- [.vercelignore](.vercelignore) and the function exclusions keep local virtual environments, tests, environment files, and Firebase service-account files out of uploads/bundles.
- [requirements.txt](requirements.txt) is installed by Vercel. The obsolete `supafunc` pin was removed because it conflicts with the current HTTPX pin; the application uses `supabase-functions` through Supabase instead.

## Configure environment variables

Set these in **Project Settings → Environment Variables**, separately for Preview and Production. Names are case-insensitive in [core/config.py](core/config.py), but **use exactly uppercase `CRON_SECRET`** so Vercel attaches it to scheduled requests. Do not upload `.env.production` or commit credentials.

| Variable | Purpose |
| --- | --- |
| `APP_ENV` | `production` on Vercel. |
| `APP_VERSION` | Version returned by `/`. |
| `SUPABASE_URL`, `SUPABASE_KEY` | Supabase project URL and server-side API/service-role key; never expose the key to the frontend. |
| `FIREBASE_SERVICE_ACCOUNT_JSON` | Entire service-account JSON as an environment value, including the private key with JSON-escaped newlines. Required on Vercel. |
| `CRON_SECRET` | Random shared secret of at least 32 characters. |
| `OPEN_EXCHANGE_RATES_APP_ID` | Forex data provider key. |
| `AZURE_FOUNDRY_API_KEY`, `AZURE_FOUNDRY_PROJECT_URL` | Existing AI provider credentials and endpoint. |
| `AZURE_FOUNDRY_PROJECT_MODEL_NAME`, `AZURE_FOUNDRY_PROJECT_API_VERSION` | Chat/insight model deployment and API version. |
| `HUGGINGFACE_API_KEY`, `OPENROUTER_API_KEY` | Fallback AI credentials; explicitly set empty strings if unused. |
| `SMTP_HOST`, `SMTP_PORT` | SMTP SSL endpoint and port (typically 465). |
| `SMTP_USERNAME`, `SMTP_PASSWORD` | SMTP credentials; use an app password where required. |
| `FROM_EMAIL`, `FROM_NAME` | Email sender identity. |
| `ALLOWED_ORIGINS` | Comma-separated frontend origins, e.g. `https://your-frontend.example`. Set explicitly in production. |
| `API_BASE_URL` | Public backend origin, e.g. `https://mali-backend.vercel.app`; used by the local scheduler's HTTP calls. |

All existing settings fields are required at startup even when a feature is unused. `FIREBASE_SERVICE_ACCOUNT_JSON` is read through the case-insensitive settings loader, so uppercase Vercel variables and existing lowercase local variables both work. A nonempty JSON value takes priority in every environment. Only local non-production environments may fall back to the untracked `firebase/firebase-service-account.json`; `APP_ENV=prod`, `APP_ENV=production`, and `VERCEL=1` require the environment value. Invalid/missing credentials fail startup with a configuration error. Keep Vercel's system environment variables enabled (`VERCEL=1`) so the background scheduler stays disabled.

## Database preparation

Apply [db/supabase_schema.sql](db/supabase_schema.sql) to the intended Supabase project from a trusted environment, not during the Vercel build. Check that the live schema also matches the current service queries. In particular, monthly archives need `user_impact_profiles`, `monthly_spending`, and a unique `(user_id, month)` constraint for the existing upsert. Confirm Firebase, AI, forex, and SMTP credentials against staging resources before production.

## Cron jobs

Vercel sends authenticated **GET** requests using `Authorization: Bearer <CRON_SECRET>` and runs crons only on production deployments. Existing `POST /fetch/*` requests with `x-cron-secret` remain supported. Missing/incorrect credentials are rejected before work starts; an empty configured secret fails closed. Successful responses use `Cache-Control: no-store`.

| Job | Path | UTC expression | Africa/Nairobi schedule |
| --- | --- | --- | --- |
| Forex + insight | `/fetch/forex` | `0 4 * * *` | Daily at 07:00 |
| Fuel + insight | `/fetch/fuel` | `0 4 15 * *` | Monthly on the 15th at 07:00 |
| Food basket + insight | `/fetch/food` | `0 4 * * 1` | Mondays at 07:00 |
| News feed | `/fetch/feed` | `0 4 * * *` | Daily at 07:00 |
| Monthly spending snapshot | `/cron/monthly-spending` | `0 21 28-31 * *` | First day of the month at 00:00 |

Nairobi is UTC+3 year-round. Midnight on the first is 21:00 UTC on the previous month's last day. Since Vercel cron cannot express a variable last day, the archive route checks Nairobi's date and skips non-first-day invocations. At the scheduled time the existing archive records the month just ended using the UTC date. Do not use this endpoint as a general late-month backfill tool.

APScheduler still runs locally/on persistent hosts, with explicit Nairobi timezones. It does not start on Vercel. Disable any older external scheduler calling the same jobs to avoid duplicate runs.

Hobby supports at most one execution per day per job, with execution within the scheduled hour rather than exact-minute timing. These expressions meet that frequency limit. Use a suitable paid plan for precise timing and review current quotas.

Jobs execute within the HTTP request, not detached background tasks. Archive failures return HTTP 500 rather than a false success. Vercel does not automatically retry failed cron invocations. Inspect logs before manually retrying: monthly snapshots skip existing user/month records, but fetchers/insights are not globally exactly-once and concurrent retries can duplicate data.

## Deploy

1. Import this repository at [vercel.com/new](https://vercel.com/new).
2. Set the root to this repository and the framework to **FastAPI**. Remove imported custom build/install/output overrides; use framework defaults and enable Fluid compute for the configured duration.
3. Configure the environment variables above. [.python-version](.python-version) selects Python 3.12 explicitly. The deployment regression tests pass in a clean Python 3.12 environment as well as the existing Python 3.11 environment. Verify the deployed build and cold start before promotion.
4. Deploy a preview and run the health, auth, database, email, CORS, and REST chat checks below. A preview does not run cron automatically.
5. Deploy/promote to production. Confirm all five jobs under **Settings → Cron Jobs** and inspect their first execution logs.

If the Vercel CLI is already installed, `vercel` creates a preview and `vercel --prod` deploys production. Neither is required for dashboard deployment.

## Verification

The reference Enabled Loan Tracker backend uses a legacy `api/index.py` bridge and catch-all routes. Mali already exports `main:app`, which Vercel's current native FastAPI integration supports directly. Do not mix the two routing configurations or copy the reference project's environment files.

Validation performed for this configuration:

- 30 regression tests passed on Python 3.11 and in a fresh Python 3.12 environment, with generated test credentials and no external service requests.
- A clean install of the exact requirements passed `pip check`; Linux x86_64 Python 3.12 binary-wheel dependency resolution also succeeded.
- Tests cover Firebase environment/file handling, cold start, health/docs/OpenAPI, CORS, scheduler suppression, authenticated cron GET/legacy POST routes, monthly date guards, and email template loading outside the project directory.

These checks do not replace a Vercel build or live provider verification.

```bash
# Focused regression tests (external services are mocked)
virtual/bin/python -m pytest tests/test_vercel.py -q

# Local server, using this project's existing virtual environment
virtual/bin/python -m uvicorn main:fast_api_app --reload

# Deployed health and schema checks
curl --fail https://your-project.vercel.app/health
curl --fail https://your-project.vercel.app/openapi.json

# Must return 401 without credentials and perform no fetching
curl -i https://your-project.vercel.app/fetch/forex
```

Interactive docs are at `/docs`. Routes keep their existing prefixes (`/auth`, `/dashboard`, `/impact`, `/feed`, `/profile`, `/mali`, `/fetch`). There is no `/server` prefix. `/health` is a process check, not proof of working external services.

For a controlled staging fetch, set `CRON_SECRET` in your shell without putting its value in history, then call:

```bash
curl --fail --header "Authorization: Bearer $CRON_SECRET" \
  https://your-project.vercel.app/fetch/forex
```

This writes data and may incur AI-provider charges. Use staging credentials. Test real authentication, a database-backed API route, email delivery, and `POST /mali/chat` separately.

## Serverless limits and troubleshooting

- **WebSockets:** Vercel now supports FastAPI WebSockets in public beta on Fluid compute. The existing `/mali/chat/ws` route can be used, but connections close at the function's maximum duration (300 seconds here). Verify the deployed upgrade/stream and implement frontend reconnects with resubmitted chat history; reconnects can reach a different instance. `POST /mali/chat` remains the non-streaming alternative.
- **Long jobs:** Feed scraping/AI enrichment and all-user archives can exceed the 300-second budget as data grows. Measure production durations. If they exceed the budget, move the work to a durable external worker or implement resumable batches before relying on it; raising a timeout alone does not guarantee completion.
- **Build/import failures:** Check required settings and JSON credentials, then dependency installation and bundle size. The AI/database SDKs include native dependencies; the local virtual environment is never uploaded.
- **Firebase failures:** Set the JSON environment value, redeploy, and verify that it belongs to the client application's Firebase project. Never commit a service-account key to fix an import error.
- **Cron 401/503:** Check uppercase `CRON_SECRET`, redeploy after changes, and ensure deployment protection permits Vercel's production cron requests.
- **CORS/email/database failures:** Check `ALLOWED_ORIGINS`, SMTP SSL credentials/port, and the Supabase schema and backend permissions respectively.

Review function error rates, durations, cron logs, and provider quotas after deployment. To roll back, promote the last known-good deployment in the Vercel dashboard; environment or database changes may need separate rollback.

## References

- [Vercel FastAPI integration](https://vercel.com/docs/frameworks/backend/fastapi)
- [Python runtime](https://vercel.com/docs/functions/runtimes/python)
- [Managing cron jobs](https://vercel.com/docs/cron-jobs/manage-cron-jobs)
- [Cron limits](https://vercel.com/docs/cron-jobs/usage-and-pricing)
- [WebSocket support and connection limits](https://vercel.com/kb/guide/do-vercel-serverless-functions-support-websocket-connections)
- [Deployment checklist](#deployment-checklist)

Configuration preparation is not a completed deployment. Live credentials, deployed build/cold-start checks, service smoke tests, and cron duration checks remain required.

## Deployment checklist

Use the configuration guidance above and complete the unchecked items against the target environment before relying on production traffic or scheduled jobs.

### Repository preparation

- [x] [main.py](main.py) exports `app` for native FastAPI deployment and retains the local `fast_api_app` export.
- [x] [vercel.json](vercel.json) declares all five cron jobs and a 300-second function limit.
- [x] Fetcher routes accept authenticated GET requests and retain legacy POST support.
- [x] Monthly spending has an authenticated, date-guarded cron route.
- [x] APScheduler is disabled when `VERCEL=1` and retains Nairobi schedules on persistent hosts.
- [x] Firebase accepts service-account JSON from environment configuration.
- [x] [.vercelignore](.vercelignore) and function exclusions omit virtual environments and credential files without excluding email templates.
- [ ] Review and commit only intended project changes. Never commit environment files or service-account keys.

### Vercel settings

- [ ] Import the repository using the repository root and **FastAPI** framework.
- [ ] Clear imported build/install/output overrides; use framework defaults.
- [ ] Enable Fluid compute and confirm the configured duration fits the selected plan.
- [ ] Confirm the build uses Python 3.12 as selected by [.python-version](.python-version).
- [ ] Keep system environment variables enabled so `VERCEL=1` is available.
- [ ] Set all settings from the [environment table](#configure-environment-variables), scoped separately for Preview and Production.
- [ ] Set uppercase `CRON_SECRET` to a strong random value and set `FIREBASE_SERVICE_ACCOUNT_JSON` to valid JSON.
- [ ] Set `ALLOWED_ORIGINS` to actual frontend origins and `API_BASE_URL` to the backend URL.
- [ ] Confirm the function bundle excludes local secrets and stays within the current Vercel size limit.

### External services

- [ ] Apply/check [db/supabase_schema.sql](db/supabase_schema.sql) against the intended Supabase database; verify current service queries match the live schema.
- [ ] Verify backend Supabase permissions and the unique `(user_id, month)` constraint required by monthly spending upserts.
- [ ] Verify Firebase ID tokens against the intended Firebase project.
- [ ] Verify configured AI providers and model deployments, including provider quotas.
- [ ] Verify the Open Exchange Rates key and reachable data sources.
- [ ] Verify SMTP SSL credentials, sender identity, and password-reset/verification delivery.

### Preview smoke tests

- [ ] Deployment installs dependencies and cold-starts successfully without local credential files.
- [ ] `/health` returns `{"status":"healthy"}` and `/docs` loads without a `/server` prefix.
- [ ] A database-backed dashboard/impact/profile request succeeds.
- [ ] Firebase-authenticated flows work and invalid tokens fail.
- [ ] Frontend CORS checks succeed.
- [ ] `POST /mali/chat` returns an answer.
- [ ] If using `/mali/chat/ws`, verify Vercel's Fluid compute WebSocket beta and test frontend reconnect/history handling when the 300-second connection budget expires.
- [ ] Every cron path rejects missing or incorrect credentials before doing any work.
- [ ] Controlled authenticated cron calls work against staging resources; these calls write data and can incur AI charges.

### Production cron verification

- [ ] All five jobs appear in **Settings → Cron Jobs** after production deployment.
- [ ] Forex and feed run daily at 07:00 Nairobi (`0 4 * * *` UTC).
- [ ] Fuel runs on the 15th at 07:00 Nairobi (`0 4 15 * *` UTC).
- [ ] Food runs Monday at 07:00 Nairobi (`0 4 * * 1` UTC).
- [ ] Monthly spending checks run at 21:00 UTC on days 28–31 and archive only on Nairobi's first day of the month.
- [ ] Account for Hobby's within-the-hour timing; use a plan with suitable precision if required.
- [ ] Disable previous external schedules for these jobs to prevent duplicate executions.
- [ ] Inspect logs and database output, not just HTTP success, for the first executions.
- [ ] Measure feed and all-user archive durations under realistic load. If they exceed 300 seconds, add resumable batches or an external worker before depending on them.
- [ ] Establish a manual retry procedure; Vercel does not automatically retry failed cron requests, and not all fetcher/insight writes are idempotent.

### Operations

- [ ] Monitor cron failures, function duration/errors, and external-service quotas.
- [ ] Configure Supabase backups and error alerts.
- [ ] Retain a known-good deployment for rollback; review environment/database changes separately.

**Status:** Repository configuration prepared; deployment and live-service verification are still required.

