# Mali Backend — Vercel Deployment Checklist

Use the [deployment guide](VERCEL_DEPLOYMENT.md) for configuration details. Complete the unchecked items against the target environment before relying on production traffic or scheduled jobs.

## Repository preparation

- [x] [main.py](main.py) exports `app` for native FastAPI deployment and retains the local `fast_api_app` export.
- [x] [vercel.json](vercel.json) declares all five cron jobs and a 300-second function limit.
- [x] Fetcher routes accept authenticated GET requests and retain legacy POST support.
- [x] Monthly spending has an authenticated, date-guarded cron route.
- [x] APScheduler is disabled when `VERCEL=1` and retains Nairobi schedules on persistent hosts.
- [x] Firebase accepts service-account JSON from environment configuration.
- [x] [.vercelignore](.vercelignore) and function exclusions omit virtual environments and credential files without excluding email templates.
- [ ] Review and commit only intended project changes. Never commit environment files or service-account keys.

## Vercel settings

- [ ] Import the repository using the repository root and **FastAPI** framework.
- [ ] Clear imported build/install/output overrides; use framework defaults.
- [ ] Enable Fluid compute and confirm the configured duration fits the selected plan.
- [ ] Confirm the Python runtime selected during the build; local validation uses Python 3.11 in [virtual/](virtual/), whereas Vercel currently defaults to 3.12.
- [ ] Keep system environment variables enabled so `VERCEL=1` is available.
- [ ] Set all settings from the [environment table](VERCEL_DEPLOYMENT.md#configure-environment-variables), scoped separately for Preview and Production.
- [ ] Set uppercase `CRON_SECRET` to a strong random value and set `FIREBASE_SERVICE_ACCOUNT_JSON` to valid JSON.
- [ ] Set `ALLOWED_ORIGINS` to actual frontend origins and `API_BASE_URL` to the backend URL.
- [ ] Confirm the function bundle excludes local secrets and stays within the current Vercel size limit.

## External services

- [ ] Apply/check [db/supabase_schema.sql](db/supabase_schema.sql) against the intended Supabase database; verify current service queries match the live schema.
- [ ] Verify backend Supabase permissions and the unique `(user_id, month)` constraint required by monthly spending upserts.
- [ ] Verify Firebase ID tokens against the intended Firebase project.
- [ ] Verify configured AI providers and model deployments, including provider quotas.
- [ ] Verify the Open Exchange Rates key and reachable data sources.
- [ ] Verify SMTP SSL credentials, sender identity, and password-reset/verification delivery.

## Preview smoke tests

- [ ] Deployment installs dependencies and cold-starts successfully without local credential files.
- [ ] `/health` returns `{"status":"healthy"}` and `/docs` loads without a `/server` prefix.
- [ ] A database-backed dashboard/impact/profile request succeeds.
- [ ] Firebase-authenticated flows work and invalid tokens fail.
- [ ] Frontend CORS checks succeed.
- [ ] `POST /mali/chat` returns an answer.
- [ ] If using `/mali/chat/ws`, verify Vercel's Fluid compute WebSocket beta and test frontend reconnect/history handling when the 300-second connection budget expires.
- [ ] Every cron path rejects missing or incorrect credentials before doing any work.
- [ ] Controlled authenticated cron calls work against staging resources; these calls write data and can incur AI charges.

## Production cron verification

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

## Operations

- [ ] Monitor cron failures, function duration/errors, and external-service quotas.
- [ ] Configure Supabase backups and error alerts.
- [ ] Retain a known-good deployment for rollback; review environment/database changes separately.

**Status:** Repository configuration prepared; deployment and live-service verification are still required.

