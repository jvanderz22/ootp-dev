"""Single shared-password HTTP Basic auth for the app's API surface.

Set APP_PASSWORD (and optionally APP_USERNAME, default "admin"). If APP_PASSWORD
is unset the middleware is a no-op so local dev / tests don't need it.

Deny-by-default: every mutating request needs credentials, and so do the GET
data endpoints under _ALWAYS_PROTECT. Only safe GETs for the Angular SPA shell
and its static assets pass through unauthenticated, so the in-app /login page
can render; it collects the shared password and sends it as an Authorization
header on every API call.
"""
import base64
import hmac
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import PlainTextResponse

# GET data endpoints that a plain browser navigation could otherwise reach.
# /healthz is here on purpose: the login page probes it to validate the entered
# password before storing the token.
_ALWAYS_PROTECT = ("/graphql", "/download", "/healthz")


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


def _requires_auth(request) -> bool:
    if request.method == "OPTIONS":
        return False  # CORS preflight never carries credentials
    if request.method not in ("GET", "HEAD"):
        return True  # every mutation / POST, including GraphQL queries
    return request.url.path.startswith(_ALWAYS_PROTECT)


class BasicAuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _requires_auth(request):
            return await call_next(request)
        if _authorized(request.headers.get("authorization", "")):
            return await call_next(request)
        # No WWW-Authenticate header: the SPA's /login page handles credentials,
        # so we don't want the browser's native Basic-auth dialog.
        return PlainTextResponse("Authentication required", status_code=401)
