"""Rate limiting configuration for MomentLoop."""

from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.config import get_settings

settings = get_settings()

# Create limiter using client IP address as the key
limiter = Limiter(key_func=get_remote_address)
