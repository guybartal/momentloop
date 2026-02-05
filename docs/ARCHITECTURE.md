# MomentLoop - Architecture & Design Document

> AI-Powered Memory Video Generator

## Overview

MomentLoop is a full-stack web application that transforms user photos into stylized, animated memory videos using AI. Users upload images, apply artistic styles, generate animation prompts, create video clips, and export a final stitched video.

## Core Workflow

```
Upload Photos → Apply AI Styles → Generate Animation Prompts → Create Videos → Export
```

1. **Upload Photos** - Users upload images to a project
2. **Apply AI Styles** - Transform photos using styles like Studio Ghibli, LEGO, Minecraft, or The Simpsons (powered by Google Gemini)
3. **Generate Animation Prompts** - AI analyzes each photo and suggests cinematic animations (camera movements, effects, actions)
4. **Create Videos** - Each styled photo becomes a 5-second animated video clip (using Kling AI via fal.ai)
5. **Export** - Stitch all clips together into a final video using FFmpeg

---

## Tech Stack

| Layer | Technology |
|-------|------------|
| Frontend | React 18 + TypeScript, Vite, Tailwind CSS, Zustand |
| Backend | FastAPI (Python), SQLAlchemy, PostgreSQL |
| AI Services | Google Gemini (style transfer & prompts), Kling 2.1 (video generation) |
| DevOps | Docker Compose, WebSockets for real-time updates |

---

## Project Structure

```
momentloop/
├── frontend/                 # React SPA
│   ├── src/
│   │   ├── components/       # Reusable UI components
│   │   ├── pages/            # Route pages (Login, Dashboard, Project, Export)
│   │   ├── stores/           # Zustand state management
│   │   ├── services/         # API client (axios)
│   │   └── types/            # TypeScript interfaces
│   └── package.json
│
├── backend/                  # FastAPI application
│   ├── app/
│   │   ├── routers/          # API endpoints
│   │   ├── services/         # AI integrations & business logic
│   │   ├── models/           # SQLAlchemy ORM models
│   │   ├── schemas/          # Pydantic request/response schemas
│   │   └── core/             # Config, security, dependencies
│   ├── alembic/              # Database migrations
│   └── requirements.txt
│
├── storage/                  # File storage (mounted volume)
│   ├── uploads/              # Original user photos
│   ├── styled/               # Style-transferred images
│   ├── videos/               # Generated scene/transition videos
│   └── exports/              # Final combined videos
│
└── docker-compose.yml
```

---

## Database Schema

### Entity Relationships

```
User (1) ──── (N) Project (1) ──┬── (N) Photo (1) ──── (N) StyledVariant
                                ├── (N) Video
                                └── (N) Export
```

### Models

| Model | Purpose |
|-------|---------|
| **User** | Authentication, OAuth tokens (Google), owns projects |
| **Project** | Container for a creative work, tracks style settings and status |
| **Photo** | Individual image with original path, styled path, animation prompt, position |
| **StyledVariant** | Multiple style variations per photo for comparison |
| **Video** | Generated clips (scene or transition type), references photos |
| **Export** | Final combined video file with status tracking |

---

## Backend Services

### ImagenService (`services/imagen.py`)
- **Purpose**: Style transfer using Google Gemini
- **Styles**: Studio Ghibli, LEGO, Minecraft, The Simpsons
- **Fallback Chain**: SDK → REST API → PIL filters
- **Creates**: StyledVariant records for comparison

### PromptGeneratorService (`services/prompt_generator.py`)
- **Purpose**: Generate cinematic animation prompts
- **Model**: Gemini 2.0 Flash
- **Output**: Subject actions, camera movements, environmental effects
- **Features**: Regeneration with user feedback, status tracking

### FalAIService (`services/fal_ai.py`)
- **Purpose**: Video generation from styled images
- **Model**: Kling 2.1/2.5 via fal.ai
- **Types**: Scene videos (5s) and transition videos (3s)
- **Features**: Async polling, retry with exponential backoff

### FFmpegService (`services/ffmpeg.py`)
- **Purpose**: Video concatenation and export
- **Features**: Multi-codec support, cleanup policies

---

## API Routes

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/auth/google` | GET | Initiate Google OAuth |
| `/api/auth/callback` | GET | OAuth callback handler |
| `/api/auth/user` | GET | Get current user |
| `/api/projects` | GET/POST | List/create projects |
| `/api/projects/{id}` | GET/PATCH/DELETE | Project CRUD |
| `/api/projects/{id}/photos` | POST | Upload photos |
| `/api/projects/{id}/styles` | POST | Apply style transfer |
| `/api/projects/{id}/prompts` | POST | Generate animation prompts |
| `/api/projects/{id}/videos` | POST | Generate videos |
| `/api/projects/{id}/exports` | POST | Create final export |
| `/storage/*` | GET | Serve stored files |
| `/ws/projects/{projectId}` | WebSocket | Real-time updates |

---

## Frontend Pages

| Page | Route | Purpose |
|------|-------|---------|
| **LoginPage** | `/login` | Google OAuth authentication |
| **DashboardPage** | `/` | List projects, create new, delete |
| **ProjectPage** | `/projects/:id` | Main editor: upload, style, prompt, video |
| **ExportPage** | `/projects/:id/export` | Final video preview and download |

### Key Components

- `ImageUploader` - Drag-drop file upload
- `PhotoGallery` - Grid with drag-and-drop reordering
- `StyleSelector` - Style picker with previews
- `PromptEditor` - Animation prompt display and editing
- `VideoPreview` - Video playback with status
- `GooglePhotosPicker` - Import from Google Photos

---

## Concurrency Control

The backend uses `SemaphoreManager` to prevent API rate limiting and resource exhaustion:

| Operation | Max Concurrent | Reason |
|-----------|----------------|--------|
| Style Transfers | 3 | CPU/API intensive |
| Video Generations | 5 | Kling API limits |
| Prompt Generations | 5 | Gemini API limits |
| Exports | 2 | FFmpeg resource intensive |

---

## Real-time Updates

WebSocket connections provide real-time status updates:

| Event | Trigger |
|-------|---------|
| `photo_styled` | Style transfer completes |
| `video_ready` | Video generation completes |
| `export_complete` | Final export ready |

---

## Configuration

Key environment variables (`.env`):

```
# Database
DATABASE_URL=postgresql+asyncpg://...

# Auth
GOOGLE_CLIENT_ID=
GOOGLE_CLIENT_SECRET=
JWT_SECRET=
JWT_EXPIRATION_HOURS=

# AI Services
GOOGLE_GEMINI_API_KEY=
FAL_KEY=

# App Config
CORS_ORIGINS=
RATE_LIMIT_PER_MINUTE=
FILE_RETENTION_DAYS=
```

---

## Design Decisions

1. **Triple Fallback for Style Transfer** - SDK → REST API → PIL filters ensures functionality even when APIs fail

2. **Semaphore-based Concurrency** - Prevents overwhelming external APIs while maximizing throughput

3. **Status Tracking** - All async operations use `pending → generating → completed → failed` states

4. **Multiple Style Variants** - Users can compare different style outputs before committing

5. **WebSocket Integration** - Real-time updates eliminate polling overhead

6. **Background Tasks** - Long-running operations use asyncio background tasks

7. **Retry with Exponential Backoff** - Handles transient API failures gracefully

8. **Google Photos Integration** - Seamless import from existing photo libraries

---

## Future Considerations

- Additional AI style options
- Custom style prompt training
- Audio/music integration for exports
- Social sharing features
- Batch processing optimizations
- CDN integration for storage
