from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import auth, dashboard, impact, feed, fetchers, mali_chat, profile
from core.config import settings
from tasks.scheduler import start_scheduler, stop_scheduler

fast_api_app = FastAPI(
    title="Mali API",
    description="Kenyan financial intelligence — real data, real impact.",
    version="1.0.0",
)

fast_api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Startup/Shutdown Events ────────────────────────────────────────────────────────────
@fast_api_app.on_event("startup")
async def startup_event():
    """Initialize background scheduler on app startup"""
    start_scheduler()

@fast_api_app.on_event("shutdown")
async def shutdown_event():
    """Stop background scheduler on app shutdown"""
    stop_scheduler()

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
    return {"status": "ok", "app": "Mali Mind Backend", "version": settings.app_version}


@fast_api_app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}