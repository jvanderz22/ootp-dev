"""Single shared-password HTTP Basic auth for the whole app.

Set APP_PASSWORD (and optionally APP_USERNAME, default "admin"). If APP_PASSWORD
is unset the middleware is a no-op so local dev / tests don't need it.
"""
import base64
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

_REALM = "OOTP Draft"


def _expected():
    return os.environ.get("APP_USERNAME", "admin"), os.environ.get("APP_PASSWORD", "")


def _authorized(header: str) -> bool:
    username, password = _expected()
    if not password:
        return True
    if not header or not header.lower().startswith("basic "):
        return False
    try:
        decoded = base64.b64decode(header.split(" ", 1)[1]).decode("utf-8")
        got_user, got_pass = decoded.split(":", 1)
    except (ValueError, UnicodeDecodeError):
        return False
    return hmac.compare_digest(got_user, username) and hmac.compare_digest(got_pass, password)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if _authorized(request.headers.get("authorization", "")):
            return await call_next(request)
        return PlainTextResponse(
            "Authentication required",
            status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{_REALM}"'},
        )
