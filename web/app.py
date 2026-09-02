"""ASGI host: Basic-auth + GraphQL at /graphql + CSV download + the Angular SPA.

    uvicorn web.app:app --host 0.0.0.0 --port 8080
"""
import os
from pathlib import Path

from ariadne import format_error
from ariadne.asgi import GraphQL
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from statsplus_api import StatsPlusAuthError, StatsPlusError
from web.auth import BasicAuthMiddleware
from web.schema import schema
from web.service import InvalidInput, NotFound, upload_csv_bytes

DEV = os.environ.get("DEV") == "1"
_FRONTEND_DIST = Path(
    os.environ.get(
        "FRONTEND_DIST",
        Path(__file__).parent.parent / "frontend" / "dist" / "draft-web" / "browser",
    )
)

_APP_ERRORS = (NotFound, InvalidInput, StatsPlusAuthError, StatsPlusError)


def _error_formatter(error, debug=False):
    formatted = format_error(error, debug)
    original = getattr(error, "original_error", None)
    if isinstance(original, _APP_ERRORS):
        formatted["message"] = str(original)
        formatted.setdefault("extensions", {})["code"] = type(original).__name__
    return formatted


graphql_app = GraphQL(schema, debug=DEV, error_formatter=_error_formatter)


async def download_upload_csv(request):
    name = request.path_params["name"]
    try:
        body = upload_csv_bytes(name)
    except NotFound as exc:
        return JSONResponse({"error": str(exc)}, status_code=404)
    except InvalidInput as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return Response(
        body,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{name}-c-plus.csv"'},
    )


async def healthz(_request):
    return JSONResponse({"ok": True})


class SPAStaticFiles(StaticFiles):
    """Serve built Angular files, falling back to index.html for client routes."""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


async def graphql_no_slash(request):
    # Apollo posts to /graphql; the ASGI GraphQL app lives at /graphql/.
    target = "/graphql/"
    if request.url.query:
        target += "?" + request.url.query
    return RedirectResponse(target, status_code=307)


routes = [
    Route("/healthz", healthz),
    Route("/download/{name:path}/upload.csv", download_upload_csv),
    Route("/graphql", graphql_no_slash, methods=["GET", "POST", "OPTIONS"]),
    Mount("/graphql", graphql_app),
]

if _FRONTEND_DIST.is_dir():
    routes.append(Mount("/", app=SPAStaticFiles(directory=_FRONTEND_DIST, html=True)))


async def _warm_models():
    try:
        from scoring.model_cache import warm

        warm()
    except Exception as exc:  # best effort - models train on first request instead
        print(f"[startup] model warm-up skipped: {exc}")


app = Starlette(debug=DEV, routes=routes, on_startup=[_warm_models])
app.add_middleware(BasicAuthMiddleware)

if DEV:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
