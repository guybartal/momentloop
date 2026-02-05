# MomentLoop

Transform your photos into styled, animated memory videos.

## Overview

MomentLoop is a web application that transforms user photos into styled, animated videos. Users upload images, apply artistic styles (Studio Ghibli, Lego, Minecraft, Simpsons), generate animation prompts, create videos using AI, and stitch them into a final memory video.

## Tech Stack

- **Frontend**: React + TypeScript + Vite + Tailwind CSS
- **Backend**: Python + FastAPI
- **Database**: PostgreSQL
- **AI Services**:
  - Google Imagen (style transfer)
  - Kling 2.0 via fal.ai (video generation)

## Getting Started

### Prerequisites

- Docker and Docker Compose
- Node.js 18+ (for local frontend development)
- Python 3.11+ (for local backend development)

### Quick Start with Docker

1. Clone the repository and navigate to the project directory

2. Copy the environment file and configure it:
   ```bash
   cp .env.example .env
   # Edit .env with your API keys
   ```

3. Start all services:
   ```bash
   docker-compose up -d
   ```

4. Access the application:
   - Frontend: http://localhost:5173
   - Backend API: http://localhost:8000
   - API Docs: http://localhost:8000/docs

### Local Development

#### Backend

```bash
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

#### Frontend

```bash
cd frontend
npm install
npm run dev
```

## Project Structure

```
momentloop/
├── frontend/          # React application
├── backend/           # FastAPI application
├── storage/           # Local file storage
├── docker-compose.yml
└── README.md
```

## Environment Variables

See `.env.example` for all required environment variables.

## License

MIT
