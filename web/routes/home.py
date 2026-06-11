import os
from datetime import datetime
from fastapi import APIRouter, Request, Query
from fastapi.responses import HTMLResponse
from web.globals import get_db, get_config
from db.queries import get_clusters_for_date, get_available_dates
from web.templates import templates

router = APIRouter()

SOURCE_PRIORITY = {
    "arxiv-cs-ai": ("#1b5e20", 0.9, "arXiv"),
    "hackernews": ("#e65100", 0.7, "HN"),
    "github-trending": ("#0d47a1", 0.8, "GitHub"),
    "jiqizhixin": ("#4a148c", 0.6, "机器之心"),
    "reddit-ml": ("#b71c1c", 0.5, "Reddit"),
}


@router.get("/", response_class=HTMLResponse)
async def home(request: Request, date: str = Query(default="")):
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

    available_dates = get_available_dates(db) if db else []
    if not available_dates:
        return templates.TemplateResponse(request, "home.html", {
            "clusters": [], "show_date": datetime.now().strftime("%Y-%m-%d"),
            "empty": True, "available_dates": [], "prev_date": "", "next_date": "",
        })

    show_date = date if date and date in available_dates else available_dates[0]
    clusters = get_clusters_for_date(db, show_date)

    # Compute priority display info for each article
    for cluster in clusters:
        for article in cluster["articles"]:
            src = article.get("source_id", "")
            color, weight, label = SOURCE_PRIORITY.get(src, ("#607d8b", 0.3, src))
            article["priority_color"] = color
            article["priority_weight"] = weight
            article["source_label"] = label

    # Date navigation
    try:
        idx = available_dates.index(show_date)
    except ValueError:
        idx = 0
    prev_date = available_dates[idx + 1] if idx + 1 < len(available_dates) else ""
    next_date = available_dates[idx - 1] if idx > 0 else ""

    return templates.TemplateResponse(request, "home.html", {
        "clusters": clusters,
        "show_date": show_date,
        "empty": len(clusters) == 0,
        "available_dates": available_dates,
        "prev_date": prev_date,
        "next_date": next_date,
    })
