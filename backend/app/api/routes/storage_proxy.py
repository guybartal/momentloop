"""Storage proxy route for serving files from any storage backend."""

import logging
import mimetypes

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from app.services.storage import storage_service

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/storage/{file_path:path}")
async def serve_storage_file(file_path: str):
    """Serve a file from the storage backend.

    In local mode, this is unused (FastAPI StaticFiles handles /storage/).
    In Azure mode, this streams files from Blob Storage.
    """
    try:
        data = await storage_service.read_file(file_path)
    except (FileNotFoundError, ValueError) as e:
        raise HTTPException(status_code=404, detail="File not found") from e
    except Exception as e:
        logger.error("Error reading file %s: %s", file_path, e)
        raise HTTPException(status_code=500, detail="Error reading file") from e

    # Guess content type
    content_type, _ = mimetypes.guess_type(file_path)
    if content_type is None:
        content_type = "application/octet-stream"

    return Response(content=data, media_type=content_type)
