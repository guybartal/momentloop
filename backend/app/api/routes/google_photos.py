"""
Google Photos Picker API integration.

The old Photos Library API scopes (photoslibrary, photoslibrary.readonly, photoslibrary.sharing)
were removed on April 1, 2025. This module uses the new Photos Picker API instead.

The Picker API works differently:
1. Create a session - returns a picker URL
2. User opens the picker URL and selects photos
3. Poll the session until it's ready
4. Retrieve the selected media items
"""

import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.api.deps import get_current_user
from app.api.routes.auth import refresh_google_token
from app.api.routes.photos import generate_prompt_for_photo
from app.core.config import get_settings
from app.core.database import get_db
from app.models.photo import Photo
from app.models.project import Project
from app.models.user import User
from app.services.storage import storage_service

logger = logging.getLogger(__name__)
router = APIRouter()

GOOGLE_PHOTOS_PICKER_API = "https://photospicker.googleapis.com/v1"

# Shared HTTP client for Google Photos API
_photos_client: httpx.AsyncClient | None = None


async def _get_photos_client() -> httpx.AsyncClient:
    """Get or create a shared HTTP client for Google Photos API."""
    global _photos_client
    if _photos_client is None or _photos_client.is_closed:
        _photos_client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
    return _photos_client


class ImportPhotosRequest(BaseModel):
    session_id: str


# Retry decorator for Google Photos API calls
_api_retry = retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type(httpx.RequestError),
    reraise=True,
)


async def get_valid_google_token(user: User, db: AsyncSession) -> str:
    """Get a valid Google access token, refreshing if necessary."""
    if not user.google_access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Photos not connected. Please authorize access first.",
        )

    # Check if token is expired
    if user.google_token_expiry and user.google_token_expiry < datetime.now(UTC):
        # Try to refresh
        new_token = await refresh_google_token(user, db)
        if not new_token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google token expired. Please re-authorize.",
            )
        return new_token

    return user.google_access_token


@router.post("/google-photos/session")
async def create_picker_session(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new Google Photos Picker session.
    Returns a picker URL that the user should open to select photos.
    """
    access_token = await get_valid_google_token(current_user, db)
    client = await _get_photos_client()

    try:
        # Create a unique request ID
        request_id = str(uuid4())

        response = await client.post(
            f"{GOOGLE_PHOTOS_PICKER_API}/sessions",
            params={"requestId": request_id},
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json={},
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "session_id": data.get("id"),
                "picker_uri": data.get("pickerUri"),
                "expire_time": data.get("expireTime"),
            }
        else:
            logger.warning("Picker session creation failed: %d - %s", response.status_code, response.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to create picker session: {response.text}",
            )

    except httpx.RequestError as e:
        logger.error("Google Photos Picker API request error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Google Photos Picker API",
        )


@router.get("/google-photos/session/{session_id}")
async def get_picker_session(
    session_id: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get the status of a picker session.
    The session is ready when mediaItemsSet is true.
    """
    access_token = await get_valid_google_token(current_user, db)
    client = await _get_photos_client()

    try:
        response = await client.get(
            f"{GOOGLE_PHOTOS_PICKER_API}/sessions/{session_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            return {
                "session_id": data.get("id"),
                "picker_uri": data.get("pickerUri"),
                "media_items_set": data.get("mediaItemsSet", False),
                "expire_time": data.get("expireTime"),
            }
        elif response.status_code == 404:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Session not found or expired",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to get session: {response.text}",
            )

    except httpx.RequestError as e:
        logger.error("Google Photos Picker API request error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Google Photos Picker API",
        )


@router.get("/google-photos/session/{session_id}/media-items")
async def list_session_media_items(
    session_id: str,
    page_size: int = 50,
    page_token: str | None = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List media items that the user selected in the picker session.
    Only works after the user has finished selecting photos (mediaItemsSet is true).
    """
    access_token = await get_valid_google_token(current_user, db)
    client = await _get_photos_client()

    try:
        params = {
            "sessionId": session_id,
            "pageSize": min(page_size, 100),
        }
        if page_token:
            params["pageToken"] = page_token

        response = await client.get(
            f"{GOOGLE_PHOTOS_PICKER_API}/mediaItems",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code == 200:
            data = response.json()
            media_items = data.get("mediaItems", [])

            # Format the response
            photos = []
            for item in media_items:
                media_type = item.get("type", "")
                if media_type == "PHOTO":
                    base_url = item.get("mediaFile", {}).get("baseUrl", "")
                    photos.append({
                        "id": item.get("id"),
                        "mimeType": item.get("mediaFile", {}).get("mimeType", "image/jpeg"),
                        "baseUrl": base_url,
                        # Add size params to get the actual image
                        "downloadUrl": f"{base_url}=d" if base_url else None,
                    })

            return {
                "photos": photos,
                "nextPageToken": data.get("nextPageToken"),
            }
        elif response.status_code == 400:
            # FAILED_PRECONDITION - user hasn't finished picking
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="User has not finished selecting photos yet",
            )
        else:
            logger.warning("Failed to list media items: %d - %s", response.status_code, response.text)
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Failed to list media items: {response.text}",
            )

    except httpx.RequestError as e:
        logger.error("Google Photos Picker API request error: %s", e)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to connect to Google Photos Picker API",
        )


@router.post("/projects/{project_id}/import-google-photos")
async def import_google_photos(
    project_id: UUID,
    request: ImportPhotosRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Import photos from a completed Google Photos Picker session."""
    # Verify project ownership
    result = await db.execute(
        select(Project).where(
            Project.id == project_id,
            Project.user_id == current_user.id,
        )
    )
    project = result.scalar_one_or_none()

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found",
        )

    access_token = await get_valid_google_token(current_user, db)
    client = await _get_photos_client()

    # First, check if session is ready
    session_response = await client.get(
        f"{GOOGLE_PHOTOS_PICKER_API}/sessions/{request.session_id}",
        headers={"Authorization": f"Bearer {access_token}"},
    )

    if session_response.status_code != 200:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired",
        )

    session_data = session_response.json()
    if not session_data.get("mediaItemsSet", False):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User has not finished selecting photos yet",
        )

    # Get current max position
    result = await db.execute(
        select(Photo.position)
        .where(Photo.project_id == project_id)
        .order_by(Photo.position.desc())
        .limit(1)
    )
    max_position = result.scalar() or -1

    # Fetch all media items from the session
    all_photos = []
    page_token = None

    while True:
        params = {"sessionId": request.session_id, "pageSize": 100}
        if page_token:
            params["pageToken"] = page_token

        response = await client.get(
            f"{GOOGLE_PHOTOS_PICKER_API}/mediaItems",
            params=params,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if response.status_code != 200:
            break

        data = response.json()
        media_items = data.get("mediaItems", [])

        for item in media_items:
            if item.get("type") == "PHOTO":
                base_url = item.get("mediaFile", {}).get("baseUrl", "")
                if base_url:
                    all_photos.append({
                        "id": item.get("id"),
                        "mimeType": item.get("mediaFile", {}).get("mimeType", "image/jpeg"),
                        "downloadUrl": f"{base_url}=d",  # =d for download
                    })

        page_token = data.get("nextPageToken")
        if not page_token:
            break

    # Download and save each photo
    imported_photos = []
    errors = []

    for i, photo_info in enumerate(all_photos):
        try:
            # Download the image
            response = await client.get(
                photo_info["downloadUrl"],
                headers={"Authorization": f"Bearer {access_token}"},
                follow_redirects=True,
            )

            if response.status_code != 200:
                errors.append({"id": photo_info["id"], "error": f"Failed to download: {response.status_code}"})
                continue

            content = response.content
            mime_type = photo_info["mimeType"]

            # Determine extension from content type
            ext_map = {
                "image/jpeg": ".jpg",
                "image/png": ".png",
                "image/gif": ".gif",
                "image/webp": ".webp",
                "image/heic": ".heic",
            }
            ext = ext_map.get(mime_type, ".jpg")
            filename = f"google_photos_{photo_info['id']}{ext}"

            # Save the file
            relative_path = await storage_service.save_upload(
                content, filename, project_id
            )

            # Create photo record
            photo = Photo(
                project_id=project_id,
                original_path=relative_path,
                position=max_position + i + 1,
                status="uploaded",
            )
            db.add(photo)
            imported_photos.append(photo)

        except Exception as e:
            logger.warning("Failed to import photo %s: %s", photo_info["id"], e)
            errors.append({"id": photo_info["id"], "error": str(e)})

    await db.commit()

    # Refresh all photos to get IDs
    for photo in imported_photos:
        await db.refresh(photo)

    # Start background prompt generation for each photo
    settings = get_settings()
    logger.info(f"Starting prompt generation for {len(imported_photos)} imported photos")
    for photo in imported_photos:
        logger.info(f"Creating prompt generation task for photo {photo.id}")
        asyncio.create_task(
            generate_prompt_for_photo(photo.id, settings.database_url)
        )

    # Delete the session to clean up
    try:
        await client.delete(
            f"{GOOGLE_PHOTOS_PICKER_API}/sessions/{request.session_id}",
            headers={"Authorization": f"Bearer {access_token}"},
        )
    except Exception:
        pass  # Ignore cleanup errors

    return {
        "imported_count": len(imported_photos),
        "photos": [
            {
                "id": str(photo.id),
                "original_url": storage_service.get_url(photo.original_path),
                "position": photo.position,
            }
            for photo in imported_photos
        ],
        "errors": errors,
    }
