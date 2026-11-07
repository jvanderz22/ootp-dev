"""ASGI host: Basic-auth + GraphQL at /graphql + CSV download + the Angular SPA.

    uvicorn web.app:app --host 0.0.0.0 --port 8080
"""
import os
from pathlib import Path
from urllib.parse import parse_qs

from ariadne import format_error
from ariadne.asgi import GraphQL
from starlette.applications import Starlette
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

import ranking_engine
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


class RankingEngineScope:
    """Serve each request with the ranking engine it names - the app's engine
    toggle sends an `X-Ranking-Engine` header; a download link can say
    `?engine=`. Anything else gets the default (see ranking_engine.py)."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        engine = _requested_engine(scope) if scope["type"] == "http" else None
        if engine is None:
            await self.app(scope, receive, send)
            return
        with ranking_engine.using(engine):
            await self.app(scope, receive, send)


def _requested_engine(scope):
    header = ranking_engine.HEADER.encode()
    named = next((v.decode() for k, v in scope.get("headers", []) if k == header), None)
    if named is None:
        named = parse_qs(scope.get("query_string", b"").decode()).get("engine", [None])[0]
    return named if named in ranking_engine.ENGINES else None


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


async def _open_database():
    # Runs pending migrations before the first request - on an install that
    # predates the database that includes the one-time import of its files,
    # which takes a while on a big volume.
    import anyio

    import db

    await anyio.to_thread.run_sync(db.connect)


async def _warm_models():
    try:
        from scoring.model_cache import warm

        warm()
    except Exception as exc:  # best effort - models train on first request instead
        print(f"[startup] model warm-up skipped: {exc}")


async def _collect_season_snapshots():
    # The machine sleeps when idle, so waking up is when a season's ratings
    # snapshot gets taken (see web.service.collect_season_snapshots).
    from web.service import start_season_snapshot_collection

    start_season_snapshot_collection()


app = Starlette(
    debug=DEV,
    routes=routes,
    on_startup=[_open_database, _warm_models, _collect_season_snapshots],
)
app.add_middleware(RankingEngineScope)
app.add_middleware(BasicAuthMiddleware)

if DEV:
    from starlette.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:4200"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
