from datetime import datetime
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db, get_ai
from db.models import get_all_sources, get_recent_errors
from web.templates import templates

router = APIRouter()


@router.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")

    sources = get_all_sources(db) if db else []
    errors = get_recent_errors(db, limit=10) if db else []
    enabled_count = sum(1 for s in sources if s.get("enabled"))

    article_count_today = 0
    last_collection = None
    if db:
        digest_row = db.execute(
            "SELECT created_at FROM daily_digests WHERE date = ? ORDER BY created_at DESC LIMIT 1",
            (today,)
        ).fetchone()
        last_collection = digest_row[0] if digest_row else None
        count_row = db.execute(
            "SELECT COUNT(*) FROM digest_articles da JOIN daily_digests d ON da.digest_id = d.id WHERE d.date = ?",
            (today,)
        ).fetchone()
        article_count_today = count_row[0] if count_row else 0

    ai = get_ai()
    ai_tokens_today = ai._daily_tokens if ai and hasattr(ai, '_daily_tokens') else 0

    return templates.TemplateResponse(request, "admin.html", {
        "sources": sources,
        "errors": errors,
        "enabled_count": enabled_count,
        "last_collection": last_collection,
        "article_count_today": article_count_today,
        "ai_tokens_today": ai_tokens_today,
    })
