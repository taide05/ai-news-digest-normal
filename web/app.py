import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from .routes import home, reader, search, concepts, review

logger = logging.getLogger(__name__)

_db_conn = None
_ai_client = None
_config = None


def get_db():
    return _db_conn


def get_ai():
    return _ai_client


def get_config():
    return _config


def set_globals(db_conn, ai_client, config):
    global _db_conn, _ai_client, _config
    _db_conn = db_conn
    _ai_client = ai_client
    _config = config


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

    @app_.get("/api/health")
    async def health():
        from fastapi.responses import JSONResponse
        return JSONResponse(
            {"status": "ok", "server": "ai-news-digest"},
            headers={"x-server": "ai-news-digest"}
        )

    return app_
