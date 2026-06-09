import os
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db, get_config
from db.models import get_clusters_for_date
from web.templates import templates

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    cfg = get_config()
    needs_config = not cfg or not cfg.deepseek_api_key

    if needs_config:
        env_exists = os.path.isfile(".env")
        return templates.TemplateResponse(request, "home.html", {
            "clusters": [], "today": "", "empty": True,
            "needs_config": True, "env_exists": env_exists,
        })

    db = get_db()
    if db is None:
        return templates.TemplateResponse(request, "home.html", {"clusters": [], "today": "", "empty": True})

    today = datetime.now().strftime("%Y-%m-%d")
    clusters = get_clusters_for_date(db, today)

    return templates.TemplateResponse(request, "home.html", {
        "clusters": clusters,
        "today": today,
        "empty": len(clusters) == 0,
    })
