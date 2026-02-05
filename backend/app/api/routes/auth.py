import logging
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.core.security import create_access_token
from app.models.user import User
from app.schemas.user import GoogleUserInfo, UserResponse

logger = logging.getLogger(__name__)
router = APIRouter()
settings = get_settings()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"

# Basic scopes for login
LOGIN_SCOPES = "openid email profile"
# Google Photos Picker API scope (the old photoslibrary scopes were removed April 2025)
PHOTOS_SCOPE = "https://www.googleapis.com/auth/photospicker.mediaitems.readonly"


@router.get("/google")
@limiter.limit(settings.rate_limit_auth)
async def google_login(request: Request):
    """Redirect to Google OAuth consent screen."""
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": LOGIN_SCOPES,
        "access_type": "offline",
        "prompt": "consent",
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return RedirectResponse(url=url)


@router.get("/google/photos")
@limiter.limit(settings.rate_limit_auth)
async def google_photos_auth(request: Request, current_user: User = Depends(get_current_user)):
    """Redirect to Google OAuth with Photos scope for importing photos."""
    # Include Photos scope along with basic scopes
    params = {
        "client_id": settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri.replace("/callback", "/callback/photos"),
        "response_type": "code",
        "scope": f"{LOGIN_SCOPES} {PHOTOS_SCOPE}",
        "access_type": "offline",
        "prompt": "consent",
        "state": str(current_user.id),  # Pass user ID to link tokens
    }
    url = f"{GOOGLE_AUTH_URL}?{urlencode(params)}"
    return {"auth_url": url}


@router.get("/callback")
@limiter.limit(settings.rate_limit_auth)
async def google_callback(request: Request, code: str, db: AsyncSession = Depends(get_db)):
    """Handle Google OAuth callback."""
    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri,
            },
        )

        if token_response.status_code != 200:
            logger.warning(
                "Token exchange failed: %d - %s (redirect_uri: %s)",
                token_response.status_code,
                token_response.text,
                settings.google_redirect_uri,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {token_response.text}",
            )

        tokens = token_response.json()
        access_token = tokens.get("access_token")
        # These are extracted but unused for basic login (tokens stored only for Photos scope)
        _ = tokens.get("refresh_token")
        _ = tokens.get("expires_in", 3600)

        # Get user info from Google
        userinfo_response = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )

        if userinfo_response.status_code != 200:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to get user info from Google",
            )

        google_user = GoogleUserInfo(**userinfo_response.json())

    # Find or create user
    result = await db.execute(select(User).where(User.google_id == google_user.id))
    user = result.scalar_one_or_none()

    if not user:
        # Check if user exists by email
        result = await db.execute(select(User).where(User.email == google_user.email))
        user = result.scalar_one_or_none()

        if user:
            # Link existing user to Google account
            user.google_id = google_user.id
            if google_user.picture:
                user.avatar_url = google_user.picture
        else:
            # Create new user
            user = User(
                email=google_user.email,
                name=google_user.name,
                google_id=google_user.id,
                avatar_url=google_user.picture,
            )
            db.add(user)

    # Note: We don't store access tokens from regular login here
    # because they don't have Photos scope. Tokens are only stored
    # when user explicitly authorizes Photos access via /google/photos

    await db.commit()
    await db.refresh(user)

    # Create JWT token
    jwt_token = create_access_token(data={"sub": str(user.id)})

    # Redirect to frontend with token
    frontend_url = settings.cors_origins[0] if settings.cors_origins else "http://localhost:5173"
    return RedirectResponse(url=f"{frontend_url}/login?token={jwt_token}")


@router.get("/callback/photos")
@limiter.limit(settings.rate_limit_auth)
async def google_photos_callback(
    request: Request,
    code: str,
    state: str,
    scope: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    """Handle Google OAuth callback with Photos scope."""
    logger.debug("Photos callback - Granted scopes: %s", scope)

    # Check if photos scope was actually granted
    if scope and "photoslibrary" not in scope:
        logger.warning("Photos scope was NOT granted by user")

    # Exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": settings.google_redirect_uri.replace(
                    "/callback", "/callback/photos"
                ),
            },
        )

        if token_response.status_code != 200:
            logger.warning(
                "Photos token exchange failed: %d - %s",
                token_response.status_code,
                token_response.text,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to exchange code for token: {token_response.text}",
            )

        tokens = token_response.json()
        access_token = tokens.get("access_token")
        refresh_token = tokens.get("refresh_token")
        expires_in = tokens.get("expires_in", 3600)
        token_scope = tokens.get("scope", "")

        logger.info("Photos token exchange successful, scope: %s", token_scope)

    # Update user with new tokens
    result = await db.execute(select(User).where(User.id == state))
    user = result.scalar_one_or_none()

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    user.google_access_token = access_token
    if refresh_token:
        user.google_refresh_token = refresh_token
    user.google_token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

    await db.commit()

    # Return HTML that closes the popup window
    close_popup_html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Google Photos Connected</title>
    </head>
    <body>
        <script>
            // Signal to opener that connection is complete
            if (window.opener) {
                window.opener.postMessage({ type: 'google_photos_connected' }, '*');
            }
            // Close the popup
            window.close();
            // Fallback if popup doesn't close (e.g., not opened as popup)
            setTimeout(function() {
                document.body.innerHTML = '<p style="font-family: sans-serif; text-align: center; margin-top: 50px;">Google Photos connected! You can close this window.</p>';
            }, 500);
        </script>
        <p style="font-family: sans-serif; text-align: center; margin-top: 50px;">Connecting...</p>
    </body>
    </html>
    """
    return HTMLResponse(content=close_popup_html)


@router.get("/google/photos/status")
async def google_photos_status(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if user has Google Photos access."""
    has_token = bool(current_user.google_access_token)
    token_expired = False

    if current_user.google_token_expiry:
        token_expired = current_user.google_token_expiry < datetime.now(UTC)

    if not has_token or token_expired:
        # Try to refresh if we have a refresh token
        if current_user.google_refresh_token and token_expired:
            new_token = await refresh_google_token(current_user, db)
            if not new_token:
                return {
                    "connected": False,
                    "has_refresh_token": True,
                    "needs_reauth": True,
                }
            # Token refreshed successfully
            return {
                "connected": True,
                "has_refresh_token": True,
                "needs_reauth": False,
            }
        else:
            return {
                "connected": False,
                "has_refresh_token": bool(current_user.google_refresh_token),
                "needs_reauth": True,
            }

    # Token exists and is not expired - trust it
    # (We previously verified API access but Google APIs can have propagation delays)
    return {
        "connected": True,
        "has_refresh_token": bool(current_user.google_refresh_token),
        "needs_reauth": False,
    }


async def refresh_google_token(user: User, db: AsyncSession) -> str | None:
    """Refresh the Google access token using refresh token."""
    if not user.google_refresh_token:
        return None

    async with httpx.AsyncClient() as client:
        response = await client.post(
            GOOGLE_TOKEN_URL,
            data={
                "client_id": settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "refresh_token": user.google_refresh_token,
                "grant_type": "refresh_token",
            },
        )

        if response.status_code != 200:
            logger.warning("Token refresh failed: %s", response.text)
            return None

        tokens = response.json()
        user.google_access_token = tokens.get("access_token")
        expires_in = tokens.get("expires_in", 3600)
        user.google_token_expiry = datetime.now(UTC) + timedelta(seconds=expires_in)

        await db.commit()
        return user.google_access_token


@router.get("/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_user)):
    """Get current authenticated user."""
    return current_user


@router.post("/logout")
async def logout():
    """Logout user (client-side token removal)."""
    return {"message": "Logged out successfully"}
