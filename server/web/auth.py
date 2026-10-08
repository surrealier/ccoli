"""Shared token verification for HTTP and WebSocket dashboard access."""
import base64
import binascii
import re
from hmac import compare_digest

from fastapi import Header, HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader

_API_KEY_HEADER = APIKeyHeader(name="X-Auth-Token", auto_error=False)

_token: str = ""


def configure(token: str) -> None:
    global _token
    _token = (token or "").strip()


def auth_required() -> bool:
    return bool(_token)


def token_matches(candidate: object) -> bool:
    """Compare UTF-8 bytes in constant time without logging either token."""
    if not _token or not isinstance(candidate, str):
        return False
    try:
        return compare_digest(candidate.encode("utf-8"), _token.encode("utf-8"))
    except UnicodeError:
        return False


def _decode_utf8_base64url(value: str | None) -> str | None:
    """Decode the canonical, unpadded browser header without accepting aliases."""
    if not value or len(value) > 8192 or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None:
        return None
    try:
        raw = base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)
        if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
            return None
        return raw.decode("utf-8")
    except (binascii.Error, UnicodeError, ValueError):
        return None


async def require_auth(
    key: str | None = Security(_API_KEY_HEADER),
    encoding: str | None = Header(default=None, alias="X-Auth-Token-Encoding"),
) -> None:
    if not auth_required():
        return  # auth disabled
    candidate = key if encoding is None else _decode_utf8_base64url(key) if encoding == "utf8-base64url" else None
    if not token_matches(candidate):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing X-Auth-Token header",
        )
