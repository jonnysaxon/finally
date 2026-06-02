"""Static serving of the Next.js export (PLAN §3, §11).

The frontend is built as a static export and copied into ``app/static/`` by the
Dockerfile. FastAPI serves it at ``/`` with an SPA-style fallback to
``index.html`` for client-side routes. This is mounted AFTER all ``/api/*``
routes so the API always wins. A missing static dir is tolerated (dev mode where
the frontend runs on its own port).
"""

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

STATIC_DIR = Path(__file__).parent / "static"


class SPAStaticFiles(StaticFiles):
    """StaticFiles that falls back to index.html for unknown paths (SPA routing).

    Never masks /api/* — those routes are registered before this mount, so the
    fallback only fires for paths the API didn't claim.
    """

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                index = Path(self.directory) / "index.html"
                if index.is_file():
                    return FileResponse(index)
            raise


def mount_static(app: FastAPI, static_dir: Path = STATIC_DIR) -> None:
    """Mount the static export at ``/`` if it exists.

    If the directory is absent (dev), register a small handler so a bare ``/``
    returns a helpful message instead of a confusing 404 from an unmounted path.
    """
    if static_dir.is_dir():
        app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="static")
        return

    @app.get("/")
    async def _dev_root(request: Request):
        return {
            "status": "ok",
            "detail": "Frontend static export not found; run the frontend dev server "
            "or build the Docker image. API is available under /api/*.",
        }
