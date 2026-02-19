import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.api.routes import (
    auth,
    export,
    google_photos,
    jobs,
    photos,
    projects,
    styles,
    videos,
    websocket,
)
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.rate_limit import limiter

# Initialize logging before anything else
setup_logging()

settings = get_settings()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting %s...", settings.app_name)

    # Ensure storage directories exist
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    settings.styled_path.mkdir(parents=True, exist_ok=True)
    settings.videos_path.mkdir(parents=True, exist_ok=True)
    settings.exports_path.mkdir(parents=True, exist_ok=True)

    logger.info("Storage directories initialized")

    # Reset any jobs left running from a previous server shutdown
    from app.core.stuck_jobs import (
        detect_and_reset_stuck_jobs,
        reset_orphaned_jobs,
        resume_stuck_style_transfers,
    )

    await reset_orphaned_jobs()
    await resume_stuck_style_transfers()

    # Start periodic stuck job detection
    stuck_job_task = asyncio.create_task(detect_and_reset_stuck_jobs())
    logger.info("Stuck job detection started")

    yield

    # Shutdown
    stuck_job_task.cancel()
    logger.info("Shutting down %s...", settings.app_name)


app = FastAPI(
    title=settings.app_name,
    description="Transform your photos into styled, animated memory videos",
    version="0.1.0",
    lifespan=lifespan,
)

# Add rate limiter to app state
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["Authentication"])
app.include_router(projects.router, prefix="/api/projects", tags=["Projects"])
app.include_router(photos.router, prefix="/api", tags=["Photos"])
app.include_router(styles.router, prefix="/api", tags=["Styles"])
app.include_router(videos.router, prefix="/api", tags=["Videos"])
app.include_router(export.router, prefix="/api", tags=["Export"])
app.include_router(jobs.router, prefix="/api", tags=["Jobs"])
app.include_router(google_photos.router, prefix="/api", tags=["Google Photos"])
app.include_router(websocket.router, tags=["WebSocket"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "app": settings.app_name}


# Conditional file serving based on storage backend
if settings.storage_backend == "azure":
    # Azure mode: use proxy route to stream from Blob Storage
    from app.api.routes import storage_proxy
    app.include_router(storage_proxy.router, prefix="/api", tags=["Storage"])
else:
    # Local mode: serve files directly from disk (current behavior)
    app.mount("/storage", StaticFiles(directory=str(settings.storage_path)), name="storage")
