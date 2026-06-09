from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from web.globals import get_db
from db.models import get_article, record_read
from web.templates import templates

router = APIRouter()


@router.get("/reader/{article_id}", response_class=HTMLResponse)
async def reader(request: Request, article_id: str):
    db = get_db()
    article = get_article(db, article_id) if db else None
    if article is None:
        return HTMLResponse("Article not found", status_code=404)

    record_read(db, article_id)

    cluster_id = ""
    cluster_count = 0
    if db:
        row = db.execute(
            "SELECT ca.cluster_id, (SELECT COUNT(*) FROM cluster_articles WHERE cluster_id = ca.cluster_id) "
            "FROM cluster_articles ca WHERE ca.article_id = ? LIMIT 1",
            (article_id,)
        ).fetchone()
        if row:
            cluster_id = row[0]
            cluster_count = row[1]

    return templates.TemplateResponse(request, "reader.html", {
        "article": article,
        "cluster_id": cluster_id,
        "cluster_article_count": cluster_count,
    })
