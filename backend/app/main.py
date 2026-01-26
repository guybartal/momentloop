from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import auth, export, google_photos, photos, projects, styles, videos
from app.core.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: ensure storage directories exist
    settings.uploads_path.mkdir(parents=True, exist_ok=True)
    settings.styled_path.mkdir(parents=True, exist_ok=True)
    settings.videos_path.mkdir(parents=True, exist_ok=True)
    settings.exports_path.mkdir(parents=True, exist_ok=True)
    yield
    # Shutdown


app = FastAPI(
    title=settings.app_name,
    description="Transform your photos into styled, animated memory videos",
    version="0.1.0",
    lifespan=lifespan,
)

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
app.include_router(google_photos.router, prefix="/api", tags=["Google Photos"])


@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "app": settings.app_name}


# Mount static files for storage (after API routes to avoid conflicts)
app.mount("/storage", StaticFiles(directory=str(settings.storage_path)), name="storage")
