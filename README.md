# Mali Backend

Backend for an AI-powered Kenyan financial intelligence app that turns economic signals into simple, practical explanations for households and small businesses. The API combines scraped market data, Supabase storage, Firebase-authenticated user flows, and AI-generated summaries to answer one question clearly: what does this change mean for my day-to-day costs?

## What The Backend Does

- Serves a FastAPI API for dashboard, impact analysis, feed, profile, auth, and AI chat features.
- Stores operational data in Supabase Postgres.
- Pulls economic inputs from fuel, forex, food, and feed fetchers.
- Generates household-impact summaries with the AI insight pipeline.
- Runs a background monthly archive job for user spending snapshots.
- Supports protected mobile-app flows with Firebase ID token verification.

## Stack

- FastAPI for the HTTP and WebSocket API.
- Supabase for database access.
- Firebase Admin SDK for token verification and password updates.
- Google Gemini and OpenRouter in the insight pipeline.
- Azure AI Foundry-backed chat model for the Mali chat agent.
- APScheduler for recurring background jobs.
- Azure for hosting.
- GitHub Actions or cron callers for protected fetcher triggers.

## High-Level Architecture

1. Fetchers collect economic data such as fuel prices, forex rates, food basket values, and feed items.
2. The API persists and reads those records from Supabase.
3. The insight pipeline turns raw changes into plain-language summaries and impact scores.
4. Dashboard and impact endpoints aggregate that data into app-ready payloads.
5. Mali chat answers user questions through a tool-enabled agent that can query internal data and public web context.
6. A monthly scheduler archives spending snapshots for historical analysis.

## Project Layout

```text
.
├── main.py                     # FastAPI application entrypoint
├── start.sh                    # Local dev start command
├── requirements.txt
├── core/
│   └── config.py               # Environment-backed settings
├── db/
│   ├── client.py               # Shared Supabase client
│   └── supabase_schema.sql     # Database schema bootstrap
├── ai/
│   ├── core.py                 # Shared AI call abstraction
│   ├── insights.py             # Insight generation + persistence
│   ├── categorization.py       # Custom spending category classifier
│   └── mali_agent.py           # Mali chat agent and streaming flow
├── api/
│   ├── routes/
│   │   ├── auth.py             # Auth and password reset routes
│   │   ├── dashboard.py        # Dashboard snapshot endpoint
│   │   ├── feed.py             # Feed and Ask Mali endpoints
│   │   ├── fetchers.py         # Protected fetcher trigger routes
│   │   ├── impact.py           # Impact summary and detailed impact routes
│   │   ├── mali_chat.py        # REST + WebSocket Mali chat endpoints
│   │   └── profile.py          # Profile update route
│   ├── services/
│   │   ├── auth.py
│   │   ├── dashboard.py
│   │   ├── email_service.py
│   │   ├── feed.py
│   │   ├── impact.py
│   │   └── profile.py
│   └── templates/              # HTML email templates
├── fetchers/
│   ├── feed.py
│   ├── food.py
│   ├── forex.py
│   └── fuel.py
├── firebase/
│   ├── auth.py                 # FastAPI auth dependency
│   ├── config.py               # Firebase Admin initialization
│   └── firebase-service-account.json
└── tasks/
    └── scheduler.py            # Monthly spending archive job
```

## Prerequisites

- Python 3.11
- A Supabase project with the required schema applied
- Firebase service account credentials available at `firebase/firebase-service-account.json`
- AI credentials for the providers you intend to use

## Local Setup

### 1. Create a virtual environment and install dependencies

```bash
python3.11 -m venv virtual
source virtual/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment variables

Copy the example file and fill in the values:

```bash
cp .env.example .env
```

Current settings loaded by `core/config.py`:

| Variable | Required For | Description |
| --- | --- | --- |
| `app_env` | App boot | Environment name such as `development` or `production`. |
| `app_version` | App boot | Version returned by the root health payload. |
| `supabase_url` | Database | Supabase project URL. |
| `supabase_key` | Database | Supabase service key or API key used by the backend. |
| `huggingface_api_key` | AI | Used by shared AI code paths if enabled. |
| `openrouter_api_key` | AI | Fallback provider for insight generation. |
| `open_exchange_rates_app_id` | Fetchers | API key for forex rate collection. |
| `cron_secret` | Fetchers | Shared secret expected in the `x-cron-secret` header. |
| `azure_foundry_api_key` | Mali chat | Azure AI Foundry API key for the chat agent. |
| `azure_foundry_project_url` | Mali chat | Azure AI Foundry endpoint URL. |
| `azure_foundry_project_model_name` | Mali chat | Model deployment name used by the chat agent. |
| `azure_foundry_project_api_version` | Mali chat | API version for the Azure AI Foundry client. |
| `smtp_host` | Email | SMTP server host. |
| `smtp_port` | Email | SMTP server port. |
| `smtp_username` | Email | SMTP username. |
| `smtp_password` | Email | SMTP password. |
| `from_email` | Email | Sender address for verification and reset emails. |
| `from_name` | Email | Sender display name. |

### 3. Apply the database schema

Run `db/supabase_schema.sql` in your Supabase SQL editor.

### 4. Start the API

```bash
uvicorn main:fast_api_app --reload
```

Alternative:

```bash
./start.sh
```

Docs will be available at `http://localhost:8000/docs`.

## Runtime Behavior

### Startup and shutdown

- On startup, the app starts the APScheduler background scheduler.
- On shutdown, the scheduler is stopped cleanly.

### Scheduled job

`tasks/scheduler.py` runs a monthly archive job at midnight on the first day of each month. It stores a spending snapshot per user in the `monthly_spending` table and can also be triggered manually for a specific user from the impact flow.

## Authentication And Security

### Firebase-protected routes

These routes require an `Authorization` header in the format `Bearer <firebase-id-token>`:

- `/auth/sign-up`
- `/auth/social-auth`
- `/auth/me/{email}`
- `/auth/resend-verification`
- `/auth/verify-email`
- `/profile/update-profile`

The token is validated with the Firebase Admin SDK in `firebase/auth.py`.

### Public auth routes

These routes do not require a Firebase token:

- `/auth/forgot-password`
- `/auth/reset-password`

### Protected fetcher routes

Fetcher trigger endpoints require the `x-cron-secret` header. This is intended for cron jobs, GitHub Actions, or trusted internal callers.

## API Reference

### Health

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/` | No | Basic app status and version payload. |
| `GET` | `/health` | No | Lightweight health check. |

### Auth

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/auth/sign-up` | Firebase | Creates an email-based user record and sends a verification code. |
| `POST` | `/auth/social-auth` | Firebase | Creates or updates a Google-authenticated user. |
| `GET` | `/auth/me/{email}` | Firebase | Fetches a user by email. |
| `POST` | `/auth/resend-verification` | Firebase | Sends a new verification code, subject to throttling rules. |
| `POST` | `/auth/verify-email` | Firebase | Verifies the email using a 6-digit code. |
| `POST` | `/auth/forgot-password` | No | Sends a password reset code by email. |
| `POST` | `/auth/reset-password` | No | Resets the Firebase password with email, code, and new password. |

Relevant auth payloads:

```json
{
	"fullname": "Jane Doe",
	"email": "jane@example.com",
	"firebase_uid": "firebase-user-id"
}
```

```json
{
	"email": "jane@example.com",
	"code": "123456",
	"password": "StrongPassword123!"
}
```

### Dashboard

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/dashboard/` | No | Returns the home screen snapshot with fuel, forex, food basket, AI insight, and aggregate metrics. |

### Impact

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/impact/` | No | Returns a general market impact summary and AI explanation. |
| `GET` | `/impact/{user_id}` | No | Returns the full user-specific impact page payload, including recommendations and past spending. |
| `POST` | `/impact/profiles` | No | Creates or updates a user's impact profile and custom categories. |

Impact profile payload:

```json
{
	"user_id": 12,
	"income": "85000",
	"rent": "18000",
	"food_budget": "12000",
	"transport": "Matatu",
	"commute": "12",
	"electricity": "2500",
	"water": "800",
	"savings": "5000",
	"custom_categories": [
		{
			"label": "WiFi",
			"value": "3000"
		}
	]
}
```

### Feed And Ask Mali

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `GET` | `/feed/` | No | Returns the latest economic feed items. |
| `GET` | `/feed/ask?q=...` | No | Lightweight AI Q and A endpoint using recent fuel and forex context. |

### Mali Chat

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/mali/chat` | No | Full Mali chat endpoint with chat history support and suggested follow-up prompts. |
| `WS` | `/mali/chat/ws` | No | Streaming Mali chat endpoint over WebSocket. |

REST chat payload:

```json
{
	"message": "Why are food prices rising this month?",
	"user_id": "12",
	"chat_history": [
		{
			"role": "user",
			"content": "What changed this week?"
		}
	]
}
```

WebSocket clients should send JSON messages shaped like:

```json
{
	"message": "What does a weaker shilling mean for me?",
	"user_id": "12",
	"chat_history": []
}
```

### Profile

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `PUT` | `/profile/update-profile` | Firebase | Updates the user's full name. |

Payload:

```json
{
	"id": 12,
	"fullname": "Jane Wanjiru"
}
```

### Fetchers

| Method | Endpoint | Auth | Description |
| --- | --- | --- | --- |
| `POST` | `/fetch/fuel` | `x-cron-secret` | Runs the fuel fetcher and stores a new insight. |
| `POST` | `/fetch/forex` | `x-cron-secret` | Runs the forex fetcher and stores a new insight. |
| `POST` | `/fetch/food` | `x-cron-secret` | Runs the food fetcher and stores a new insight. |
| `POST` | `/fetch/feed` | `x-cron-secret` | Runs the news and event feed fetcher. |

Example header:

```http
x-cron-secret: your-shared-secret
```

## AI Components

### Insight pipeline

The insight pipeline in `ai/insights.py` is used by the fetcher flows and impact summaries. It generates structured JSON with:

- `summary`
- `impact_score`
- `affected_areas`

The resulting insight is stored in the `ai_insights` table.

### Mali chat agent

The chat agent in `ai/mali_agent.py` is separate from the basic insight pipeline. It can:

- Query allowlisted internal tables from Supabase.
- Search public web context.
- Generate concise mobile-friendly answers.
- Return follow-up suggestions for the frontend.

## Deployment Notes

### GitHub Actions Or Other Cron Callers

If you trigger fetchers from GitHub Actions or an external scheduler, make sure the caller includes:

- `API_BASE_URL`
- `CRON_SECRET`

## Development Notes

- CORS is currently configured with `allow_origins=["*"]`. Tighten this in production.
- Firebase service account loading is file-based, so the service account JSON must exist at startup.
- The FastAPI OpenAPI spec is the source of truth for exact response models at runtime.

## Quick Start Checklist

1. Install dependencies into a Python 3.11 virtual environment.
2. Copy `.env.example` to `.env` and fill in all required secrets.
3. Add the Firebase service account JSON under `firebase/`.
4. Apply `db/supabase_schema.sql` to Supabase.
5. Start the API with `uvicorn main:fast_api_app --reload`.
6. Open `/docs` and verify the routes you need are available.