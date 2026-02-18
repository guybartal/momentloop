# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Development Commands

### Full Stack (Docker)
```bash
docker compose up -d              # Start all services
docker compose down               # Stop all services
docker compose logs -f backend    # Tail backend logs
```

### Backend (Python/FastAPI)
```bash
cd backend
uv sync                           # Install dependencies
uv sync --extra dev               # Install with dev dependencies
uv run uvicorn app.main:app --reload     # Run dev server (port 8000)
uv run alembic upgrade head              # Run database migrations
uv run alembic revision --autogenerate -m "description"  # Create migration
```

### Frontend (React/Vite)
```bash
cd frontend
npm install                       # Install dependencies
npm run dev                       # Run dev server (port 5173)
npm run build                     # Production build (runs tsc first)
npm run lint                      # ESLint check
```

### Testing
```bash
cd backend
uv run pytest                     # Run all tests
uv run pytest tests/test_auth.py  # Run single test file
uv run pytest -k "test_name"      # Run tests matching pattern
uv run pytest --cov=app           # Run with coverage
```

### Linting & Formatting
```bash
cd backend && uv run ruff check . # Python linting (ruff)
cd backend && uv run ruff format . # Python formatting (ruff)
cd frontend && npm run lint       # TypeScript/React linting (eslint)
```

## Architecture Overview

MomentLoop transforms photos into AI-styled animated videos through a pipeline:
**Upload → Style Transfer → Animation Prompts → Video Generation → Export**

### Backend Services (`backend/app/services/`)

| Service | External API | Purpose |
|---------|--------------|---------|
| `imagen.py` | Google Gemini | Style transfer (Ghibli, LEGO, Minecraft, Simpsons) |
| `prompt_generator.py` | Gemini 2.0 Flash | Generate animation prompts for photos |
| `fal_ai.py` | Kling via fal.ai | Generate 5s video clips from styled images |
| `ffmpeg.py` | FFmpeg binary | Concatenate clips into final export |

All services use `SemaphoreManager` for concurrency control to avoid API rate limits.

### Database Models

```
User (1) ──── (N) Project (1) ──┬── (N) Photo (1) ──── (N) StyledVariant
                                ├── (N) Video
                                └── (N) Export
```

- **User**: Authentication via Google OAuth, owns projects
- **Project**: Container with style settings and overall status
- **Photo**: Original image with styled path, animation prompt, and position for ordering
- **StyledVariant**: Multiple style variations per photo for user comparison
- **Video**: Generated clips (scene=5s or transition=3s), references photos
- **Export**: Final stitched video with status tracking

### Key Patterns

- **Async everywhere**: All database operations and API calls use async/await
- **Status tracking**: Long operations use states: `pending → generating → completed → failed`
- **WebSocket updates**: Real-time notifications via `/ws/projects/{id}` for `photo_styled`, `video_ready`, `export_complete`
- **Triple fallback**: Style transfer tries SDK → REST API → PIL filters

### File Storage (`storage/`)
- `uploads/` - Original photos
- `styled/` - Style-transferred images
- `videos/` - Generated video clips
- `exports/` - Final concatenated videos

## Configuration

Backend uses Ruff for linting (line-length=100, Python 3.11+). See `backend/pyproject.toml`.

Frontend uses ESLint with TypeScript and React hooks plugins. See `frontend/package.json`.

Environment variables in `.env` - see `.env.example` for required keys (Google OAuth, Gemini API, fal.ai API).

Database uses `postgresql+asyncpg://` connection string for async SQLAlchemy.

### Testing Setup

Tests use `pytest-asyncio` with `asyncio_mode = "auto"`. The `conftest.py` provides:
- Async test client via `httpx.AsyncClient`
- In-memory SQLite for isolated database tests
- Fixtures for authenticated users and test projects
