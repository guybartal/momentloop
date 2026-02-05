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
source venv/bin/activate          # Activate virtualenv
pip install -r requirements.txt   # Install dependencies
uvicorn app.main:app --reload     # Run dev server (port 8000)
alembic upgrade head              # Run database migrations
alembic revision --autogenerate -m "description"  # Create migration
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
pytest                            # Run all tests
pytest tests/test_auth.py         # Run single test file
pytest -k "test_name"             # Run tests matching pattern
pytest --cov=app                  # Run with coverage
```

### Linting
```bash
cd backend && ruff check .        # Python linting (ruff)
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

### Data Flow

```
User → Project → Photo → StyledVariant (multiple style options)
                      → Video (scene/transition clips)
               → Export (final stitched video)
```

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
