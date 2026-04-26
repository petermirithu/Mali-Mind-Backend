from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import dashboard, impact, feed, fetchers
from core.config import settings

fast_api_app = FastAPI(
    title="MaliMind API",
    description="Kenyan financial intelligence — real data, real impact.",
    version="0.1.0",
)

fast_api_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # tighten in production
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
fast_api_app.include_router(dashboard.router)
fast_api_app.include_router(impact.router)
fast_api_app.include_router(feed.router)
fast_api_app.include_router(fetchers.router)


@fast_api_app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "app": "Mali Mind Backend", "version": settings.app_version}


@fast_api_app.get("/health", tags=["health"])
async def health():
    return {"status": "healthy"}