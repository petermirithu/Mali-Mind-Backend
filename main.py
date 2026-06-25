from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import auth, dashboard, impact, feed, fetchers, mali_chat, profile
from core.config import settings
from tasks.scheduler import start_scheduler, stop_scheduler
import logging

logger = logging.getLogger(__name__)

fast_api_app = FastAPI(
    title="Mali API",
    description="Kenyan financial intelligence — real data, real impact.",
    version="1.0.0",
)

allowed_origins_raw = settings.allowed_origins

if isinstance(allowed_origins_raw, str) and allowed_origins_raw.strip():
    allowed_origins = [o.strip() for o in allowed_origins_raw.split(",") if o.strip()]
elif isinstance(allowed_origins_raw, list):
    allowed_origins = [str(o).strip() for o in allowed_origins_raw if str(o).strip()]
else:
    allowed_origins = []

if allowed_origins:
    allow_credentials = True
else:
    allowed_origins = ["*"]
    allow_credentials = False
 
fast_api_app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=allow_credentials,    
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup/Shutdown Events ────────────────────────────────────────────────────────────
@fast_api_app.on_event("startup")
async def startup_event():
    """Initialize background scheduler on app startup"""
    start_scheduler()
    logger.info("Cron Jobs Active ⏰")

@fast_api_app.on_event("shutdown")
async def shutdown_event():
    """Stop background scheduler on app shutdown"""
    stop_scheduler()
    logger.info("Cron Jobs Stopped ⏰")

# ── Routers ───────────────────────────────────────────────────────────────────
fast_api_app.include_router(auth.router)
fast_api_app.include_router(auth.public_router)
fast_api_app.include_router(dashboard.router)
fast_api_app.include_router(impact.router)
fast_api_app.include_router(feed.router)
fast_api_app.include_router(fetchers.router)
fast_api_app.include_router(mali_chat.router)
fast_api_app.include_router(profile.router)

@fast_api_app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "app": "Mali Backend", "version": settings.app_version}


@fast_api_app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}