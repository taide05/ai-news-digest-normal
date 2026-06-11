import logging
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from .limiter import limiter
from .globals import set_globals, get_db, get_ai, get_config
from .routes import home, reader, search, concepts, review, sources, export, graph, api, admin, llm_config

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    import os
    app_ = FastAPI()
    app_.state.limiter = limiter
    app_.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    static_dir = os.path.join(os.path.dirname(__file__), "static")
    app_.mount("/static", StaticFiles(directory=static_dir), name="static")

    app_.include_router(home.router)
    app_.include_router(reader.router)
    app_.include_router(search.router)
    app_.include_router(concepts.router)
    app_.include_router(review.router)
    app_.include_router(sources.router)
    app_.include_router(export.router)
    app_.include_router(graph.router)
    app_.include_router(api.router)
    app_.include_router(admin.router)
    app_.include_router(llm_config.router)

    @app_.get("/api/health")
    async def health():
        return JSONResponse(
            {"status": "ok", "server": "ai-news-digest"},
            headers={"x-server": "ai-news-digest"}
        )

    return app_
