import os
from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db, get_config
from db.models import get_clusters_for_date
from web.templates import templates

router = APIRouter()

SOURCE_PRIORITY = {
    "arxiv-cs-ai": ("#1b5e20", 0.9),
    "hackernews": ("#e65100", 0.7),
    "github-trending": ("#0d47a1", 0.8),
    "jiqizhixin": ("#4a148c", 0.6),
    "reddit-ml": ("#b71c1c", 0.5),
}


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

    # Compute priority display info for each article
    for cluster in clusters:
        for article in cluster["articles"]:
            src = article.get("source_id", "")
            color, weight = SOURCE_PRIORITY.get(src, ("#607d8b", 0.3))
            article["priority_color"] = color
            article["priority_weight"] = weight

    return templates.TemplateResponse(request, "home.html", {
        "clusters": clusters,
        "today": today,
        "empty": len(clusters) == 0,
    })
