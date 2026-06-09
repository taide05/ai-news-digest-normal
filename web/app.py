import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .globals import set_globals, get_db, get_ai, get_config
from .routes import home, reader, search, concepts, review, sources, export

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    import os
    app_ = FastAPI()

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app_.mount("/static", StaticFiles(directory=static_dir), name="static")

    app_.include_router(home.router)
    app_.include_router(reader.router)
    app_.include_router(search.router)
    app_.include_router(concepts.router)
    app_.include_router(review.router)
    app_.include_router(sources.router)
    app_.include_router(export.router)

    @app_.get("/api/health")
    async def health():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"status": "ok", "server": "ai-news-digest"},
            headers={"x-server": "ai-news-digest"}
        )

    return app_
